"""Sales Agent — Camada 1 (Aplicação) do IIAE-BR.

Agente de **vendas** do marketplace. Fala exclusivamente o vocabulário
**Schema.org** (``Product``, ``Offer``, ``Order``, ``OrderItem``,
``PaymentChargeSpecification``). Implementa quatro comportamentos
(*behaviours*) conforme o estudo de caso (seção 3.3):

* ``ProcessarPedidoBehaviour`` (:meth:`processar_pedido`) — recebe
  solicitações de pedido, valida os dados, registra o pedido e solicita o
  cálculo de entrega ao Agente de Logística via mensagem FIPA-ACL REQUEST;
* ``ConsultarProdutoBehaviour`` (:meth:`consultar_produto`) — responde
  consultas sobre produtos do catálogo (Schema.org ``Product``/``Offer``);
* ``VerificarDisponibilidadeBehaviour`` (:meth:`verificar_disponibilidade`)
  — consulta a disponibilidade de produtos em estoque;
* ``AtualizarStatusBehaviour`` (:meth:`atualizar_status`) — atualiza o
  status de pedidos com base em mensagens INFORM da logística.

Integra-se à camada de comunicação (barramento) e, opcionalmente, à
camada de orquestração para roteamento das mensagens. Não conhece o
vocabulário GoodRelations: a tradução é responsabilidade da camada 3.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from src.layer_5_infrastructure.logging_service import get_logger
from src.utils.fipa_acl import ACLMessage, Performative

logger = get_logger(__name__)

VOCABULARY = "schema.org"


class SalesAgent:
    """Agente de vendas baseado em Schema.org.

    Parameters:
        agent_id: Identificador único do agente.
        dataset_olist: Instância de ``OlistDataset`` para consulta de
            produtos/pedidos reais. Opcional (consultas usam o catálogo
            sintético quando ausente).
        catalog: Catálogo sintético opcional (``product_id -> props``).
        stock_probability: Probabilidade-base de estoque disponível.
        rng: Gerador aleatório para reprodutibilidade.
    """

    role = "sales"
    vocabulary = VOCABULARY

    def __init__(
        self,
        agent_id: str,
        dataset_olist: Any = None,
        catalog: Optional[Dict[str, Dict[str, Any]]] = None,
        stock_probability: float = 0.85,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.agent_id = agent_id
        self.dataset = dataset_olist
        self.ontology = "schema_org"
        self.catalog = catalog or {}
        self.stock_probability = stock_probability
        self.rng = rng or random.Random()
        self.handled = 0
        # Pedidos em processamento (pedido_id -> estado)
        self.pedidos: Dict[str, Dict[str, Any]] = {}
        self._order_counter = 0

    # ------------------------------------------------------------------
    # Construção de entidades Schema.org
    # ------------------------------------------------------------------
    def build_product(self, product_id: str, **props: Any) -> Dict[str, Any]:
        """Constrói uma entidade ``schema:Product``."""
        entity = {
            "@type": "Product",
            "@id": product_id,
            "name": props.get("name", f"Produto {product_id}"),
            "sku": props.get("sku", product_id),
            "category": props.get("category", "geral"),
        }
        if "description" in props:
            entity["description"] = props["description"]
        return entity

    def build_offer(self, price: float, currency: str = "BRL",
                    availability: str = "InStock") -> Dict[str, Any]:
        """Constrói uma entidade ``schema:Offer``."""
        return {
            "@type": "Offer",
            "price": round(price, 2),
            "priceCurrency": currency,
            "availability": availability,
        }

    def build_order(self, order_number: str, status: str = "OrderProcessing",
                    date: str = "") -> Dict[str, Any]:
        """Constrói uma entidade ``schema:Order``."""
        return {
            "@type": "Order",
            "orderNumber": order_number,
            "orderStatus": status,
            "orderDate": date or "2026-01-01",
        }

    # ------------------------------------------------------------------
    # Comportamentos FIPA-ACL
    # ------------------------------------------------------------------
    def handle(self, msg: ACLMessage) -> Optional[ACLMessage]:
        """Processa uma mensagem recebida e devolve a resposta FIPA-ACL."""
        self.handled += 1
        p = msg.performative

        if p in (Performative.QUERY_IF, Performative.QUERY_REF):
            return self._handle_query(msg)
        if p == Performative.CFP:
            return self._handle_cfp(msg)
        if p == Performative.REQUEST:
            return self._handle_request(msg)
        if p == Performative.ACCEPT_PROPOSAL:
            return self._handle_accept(msg)
        return msg.create_reply(Performative.NOT_UNDERSTOOD)

    def _handle_query(self, msg: ACLMessage) -> ACLMessage:
        product_id = (msg.content or {}).get("product_id", "?")
        in_stock = self.rng.random() < self.stock_probability
        product = self.build_product(product_id)
        offer = self.build_offer(
            price=(msg.content or {}).get("price", 99.9),
            availability="InStock" if in_stock else "OutOfStock",
        )
        return msg.create_reply(
            Performative.INFORM,
            content={"product": product, "offer": offer, "inStock": in_stock},
        )

    def _handle_cfp(self, msg: ACLMessage) -> ACLMessage:
        if self.rng.random() < self.stock_probability:
            offer = self.build_offer(price=(msg.content or {}).get("price", 99.9))
            return msg.create_reply(Performative.PROPOSE, content={"offer": offer})
        return msg.create_reply(Performative.REFUSE)

    def _handle_request(self, msg: ACLMessage) -> ACLMessage:
        # Aceita o pedido e depois informa conclusão
        return msg.create_reply(Performative.AGREE)

    def _handle_accept(self, msg: ACLMessage) -> ACLMessage:
        order = self.build_order(
            order_number=(msg.content or {}).get("order_number", "ORD-0001"),
            status="OrderProcessing",
        )
        return msg.create_reply(Performative.INFORM, content={"order": order})

    # ==================================================================
    # Comportamentos do estudo de caso (seção 3.3)
    # ==================================================================

    def _next_order_id(self) -> str:
        self._order_counter += 1
        return f"{self.agent_id}-PED-{self._order_counter:06d}"

    # COMPORTAMENTO 1 — ProcessarPedidoBehaviour ------------------------
    def processar_pedido(self, pedido_data: Dict[str, Any]) -> Dict[str, Any]:
        """Recebe um pedido, valida os dados, registra-o e solicita o
        cálculo de entrega ao Agente de Logística.

        Args:
            pedido_data: Dados do pedido com ``customer_id``, ``items``
                (lista) e ``delivery_address`` (ou ``customer_zip``).

        Returns:
            Dicionário com ``pedido_id``, ``status``, ``valido`` e a
            ``mensagem`` FIPA-ACL REQUEST destinada à logística
            (``role:logistics``). Em caso de dados inválidos, retorna
            ``status="rejeitado"`` e a lista de ``erros``.
        """
        # 1. Validar dados do pedido
        valido, erros = self._validar_pedido(pedido_data)
        if not valido:
            return {
                "pedido_id": None,
                "status": "rejeitado",
                "valido": False,
                "erros": erros,
                "mensagem": None,
            }

        # 2. Registrar pedido
        pedido_id = self._next_order_id()
        items = pedido_data.get("items", [])
        peso_total = float(
            pedido_data.get(
                "total_weight_kg",
                sum(float(it.get("weight_g", 0.0)) for it in items) / 1000.0,
            )
        )
        self.pedidos[pedido_id] = {
            "pedido_id": pedido_id,
            "customer_id": pedido_data.get("customer_id"),
            "items": items,
            "seller_zip": pedido_data.get("seller_zip"),
            "customer_zip": pedido_data.get("customer_zip"),
            "peso_kg": peso_total,
            "status": "OrderProcessing",
            "order_schema": self.build_order(pedido_id, status="OrderProcessing"),
        }

        # 3. Criar mensagem FIPA-ACL REQUEST para o Agente de Logística.
        #    O conteúdo é expresso em Schema.org; a camada 3 traduz para
        #    GoodRelations antes de chegar ao agente de logística.
        conteudo = {
            "@type": "ParcelDelivery",
            "orderNumber": pedido_id,
            "origin": pedido_data.get("seller_zip"),
            "destination": pedido_data.get("customer_zip"),
            "weight": {"@type": "QuantitativeValue", "value": peso_total, "unitCode": "KGM"},
        }
        mensagem = ACLMessage(
            performative=Performative.REQUEST,
            sender=self.agent_id,
            receiver="role:logistics",
            content=conteudo,
            conversation_id=pedido_id,
            protocol="fipa-request",
            ontology="schema.org",
        )

        return {
            "pedido_id": pedido_id,
            "status": "OrderProcessing",
            "valido": True,
            "erros": [],
            "mensagem": mensagem,
        }

    @staticmethod
    def _validar_pedido(pedido_data: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Valida os campos obrigatórios do pedido."""
        erros: List[str] = []
        if not pedido_data.get("customer_id"):
            erros.append("customer_id ausente")
        items = pedido_data.get("items")
        if not items or not isinstance(items, list):
            erros.append("items ausente ou vazio")
        if pedido_data.get("customer_zip") is None and not pedido_data.get(
            "delivery_address"
        ):
            erros.append("endereço/CEP de entrega ausente")
        return (len(erros) == 0, erros)

    # COMPORTAMENTO 2 — ConsultarProdutoBehaviour -----------------------
    def consultar_produto(self, product_id: str) -> Dict[str, Any]:
        """Responde a uma consulta de produto do catálogo.

        Args:
            product_id: Identificador do produto.

        Returns:
            Entidade Schema.org ``Product`` com ``name``, ``description``,
            ``category`` e uma ``Offer`` associada (``price`` em BRL e
            ``availability``). Usa dados reais do Olist quando disponíveis.
        """
        dados = self.dataset.get_product(product_id) if self.dataset else None

        if dados is not None:
            categoria = dados.get("category_en") or dados.get(
                "product_category_name", "geral"
            )
            preco = self._preco_estimado(product_id)
            product = self.build_product(
                product_id,
                name=f"Produto {categoria} {str(product_id)[:6]}",
                category=str(categoria),
                description=(
                    f"Item da categoria {categoria}. "
                    f"Peso {dados.get('product_weight_g', 0)} g."
                ),
            )
            # Atributos físicos (úteis para o cálculo de frete na camada 1)
            product["weight"] = float(dados.get("product_weight_g", 0.0) or 0.0) / 1000.0
        else:
            categoria = "geral"
            preco = self._preco_estimado(product_id)
            product = self.build_product(product_id, category=categoria)

        disponivel = self.verificar_disponibilidade(product_id, 1)
        offer = self.build_offer(
            price=preco,
            availability="InStock" if disponivel else "OutOfStock",
        )
        return {
            "product": product,
            "offer": offer,
            "inStock": disponivel,
            "encontrado": dados is not None,
        }

    def _preco_estimado(self, product_id: str) -> float:
        """Preço estimado determinístico por produto (BRL)."""
        base = 20.0 + (hash(("preco", product_id)) % 48000) / 100.0
        return round(base, 2)

    # COMPORTAMENTO 3 — VerificarDisponibilidadeBehaviour ---------------
    def verificar_disponibilidade(self, product_id: str, quantity: int = 1) -> bool:
        """Consulta a disponibilidade de um produto em estoque.

        Args:
            product_id: Identificador do produto.
            quantity: Quantidade desejada.

        Returns:
            ``True`` se disponível, ``False`` caso contrário.
        """
        if self.dataset is not None:
            return self.dataset.is_available(
                product_id, quantity, stock_probability=self.stock_probability
            )
        # Sem dataset: usa a probabilidade-base de estoque
        return self.rng.random() < self.stock_probability

    # COMPORTAMENTO 4 — AtualizarStatusBehaviour ------------------------
    def atualizar_status(
        self, pedido_id: str, status_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Atualiza o status de um pedido com base em informações da logística.

        Args:
            pedido_id: Identificador do pedido a atualizar.
            status_info: Conteúdo (já traduzido para Schema.org) de uma
                mensagem FIPA-ACL INFORM enviada pela logística, contendo
                prazo (``estimatedDays``) e frete (``shippingCost``).

        Returns:
            O registro do pedido atualizado.
        """
        pedido = self.pedidos.get(pedido_id)
        if pedido is None:
            # Pedido desconhecido: registra de forma resiliente
            pedido = {"pedido_id": pedido_id, "status": "OrderProcessing"}
            self.pedidos[pedido_id] = pedido

        prazo = status_info.get("estimatedDays") or status_info.get("prazo_dias")
        frete = status_info.get("shippingCost") or status_info.get("valor_frete")
        novo_status = status_info.get("orderStatus", "OrderConfirmed")

        pedido["prazo_dias"] = prazo
        pedido["valor_frete"] = frete
        pedido["status"] = novo_status
        if "order_schema" in pedido:
            pedido["order_schema"]["orderStatus"] = novo_status
        return pedido

    def confirmar_pedido(self, pedido_id: str) -> Dict[str, Any]:
        """Confirma um pedido após o cálculo de prazo/frete (apoio ao UC3)."""
        pedido = self.pedidos.get(pedido_id)
        if pedido is None:
            return {"pedido_id": pedido_id, "status": "desconhecido"}
        pedido["status"] = "OrderConfirmed"
        if "order_schema" in pedido:
            pedido["order_schema"]["orderStatus"] = "OrderConfirmed"
        return pedido
