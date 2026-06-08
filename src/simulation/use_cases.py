"""Casos de uso do estudo de caso (seção 3.3) do IIAE-BR.

Implementa a execução dos **três casos de uso** do estudo de caso,
percorrendo as **cinco camadas** da arquitetura IIAE-BR e medindo a
latência total e o *overhead* por camada de cada transação:

* **UC1 — Consultar Produto e Disponibilidade**: o Agente de Vendas
  (Schema.org) responde a uma consulta de catálogo/estoque. Fluxo
  intra-vocabulário (sem tradução semântica).
* **UC2 — Calcular Prazo e Frete**: o Agente de Vendas solicita à
  Logística o cálculo de prazo/frete. Demonstra a **tradução semântica
  bidirecional** Schema.org → GoodRelations (requisição) e GoodRelations
  → Schema.org (resposta), mediada pela camada 3.
* **UC3 — Processar Pedido (ponta a ponta)**: integra UC1 + UC2,
  registrando o pedido, calculando a entrega com tradução semântica e
  atualizando o status do pedido a partir do INFORM da logística.

Cada execução atravessa as camadas:

#. **Aplicação** (camada 1) — comportamentos dos agentes;
#. **Orquestração** (camada 2) — roteamento FIPA-ACL via ``Orchestrator``;
#. **Interoperabilidade** (camada 3) — mediação semântica + cache;
#. **Comunicação** (camada 4) — barramento FIPA-ACL;
#. **Infraestrutura** (camada 5) — monitoramento/segurança.

O *overhead* por camada é amostrado pelo :class:`LayerOverheadModel`,
mantendo coerência com o motor estatístico (``engine``). A latência da
transação combina a demanda-base do caso de uso, o *overhead* das cinco
camadas e um fator de contenção opcional (carga do cenário).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Dict, List, Optional

from src.layer_1_application.logistics_agent import LogisticsAgent
from src.layer_1_application.sales_agent import SalesAgent
from src.layer_2_orchestration.orchestrator import Orchestrator
from src.layer_3_interoperability.semantic_mediator.mediator import (
    SemanticMediator,
)
from src.layer_5_infrastructure.logging_service import get_logger
from src.simulation.layer_overhead import (
    LayerOverheadAccumulator,
    LayerOverheadModel,
)
from src.utils.fipa_acl import ACLMessage, Performative

logger = get_logger(__name__)

# Demanda-base de serviço (ms) por caso de uso — tempo de processamento
# "puro" (sem overhead de camadas), calibrado a partir da complexidade do
# fluxo (número de comportamentos e traduções envolvidos).
BASE_DEMAND_MS = {
    "uc1": 4.0,    # consulta simples (1 agente, sem tradução)
    "uc2": 7.0,    # cálculo + 2 traduções semânticas
    "uc3": 11.0,   # pedido ponta a ponta (UC1 + UC2 + atualização)
}

# Carga (× baseline) em que o sistema atinge a saturação plena. A
# utilização (ρ) cresce linearmente com a carga do cenário até este
# ponto; calibrada de modo que o cenário de estresse (20×) opere em
# regime de alta contenção sem divergir.
SATURATION_LOAD = 25.0


@dataclass
class UseCaseResult:
    """Resultado da execução de um caso de uso.

    Attributes:
        use_case: Identificador do caso de uso (``uc1``/``uc2``/``uc3``).
        success: Indica se a transação foi concluída com sucesso.
        latency_ms: Latência total da transação (ms).
        layer_overhead_ms: *Overhead* por camada (ms) desta transação.
        total_overhead_ms: Soma do *overhead* das cinco camadas (ms).
        cache_hit: Indica se a tradução foi servida pelo cache semântico.
        n_translations: Número de traduções semânticas realizadas.
        steps: Trilha das mensagens/etapas FIPA-ACL do fluxo.
        payload: Dados de saída relevantes (produto, frete, pedido, ...).
    """

    use_case: str
    success: bool
    latency_ms: float
    layer_overhead_ms: Dict[str, float] = field(default_factory=dict)
    total_overhead_ms: float = 0.0
    cache_hit: bool = False
    n_translations: int = 0
    steps: List[str] = field(default_factory=list)
    payload: Dict[str, Any] = field(default_factory=dict)


# Nomes canônicos das cinco camadas (na ordem da arquitetura).
LAYER_NAMES = [
    "aplicacao",
    "orquestracao",
    "interoperabilidade",
    "comunicacao",
    "infraestrutura",
]


class UseCaseSimulator:
    """Executor dos casos de uso do estudo de caso, sobre as 5 camadas.

    Parameters:
        sales_agent: Agente de vendas (camada 1, Schema.org).
        logistics_agent: Agente de logística (camada 1, GoodRelations).
        orchestrator: Orquestrador de mensagens (camada 2).
        semantic_mediator: Mediador semântico (camada 3).
        dataset: Instância de ``OlistDataset`` (dados reais), opcional.
        overhead_model: Modelo de *overhead* por camada. Se ausente, é
            criado com ``cache_hit_rate=0`` (ajustável por
            :meth:`configure_cache`).
        rng: Gerador aleatório para reprodutibilidade.
    """

    def __init__(
        self,
        sales_agent: SalesAgent,
        logistics_agent: LogisticsAgent,
        orchestrator: Orchestrator,
        semantic_mediator: SemanticMediator,
        dataset: Any = None,
        overhead_model: Optional[LayerOverheadModel] = None,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.sales = sales_agent
        self.logistics = logistics_agent
        self.orchestrator = orchestrator
        self.mediator = semantic_mediator
        self.dataset = dataset
        self.overhead = overhead_model or LayerOverheadModel(cache_hit_rate=0.0)
        self.rng = rng or random.Random()

    # ------------------------------------------------------------------
    def configure_cache(self, cache_hit_rate: float) -> None:
        """Ajusta a taxa de acerto de cache do modelo e do mediador."""
        self.overhead.cache_hit_rate = cache_hit_rate
        self.mediator.configure_cache(cache_hit_rate)

    # ------------------------------------------------------------------
    # Utilitários internos de medição
    # ------------------------------------------------------------------
    def _sample_overhead(self) -> tuple[Dict[str, float], bool]:
        """Amostra o *overhead* por camada de uma transação."""
        breakdown, hit = self.overhead.sample(self.rng)
        return breakdown, hit

    def _finalize(
        self,
        use_case: str,
        success: bool,
        breakdown: Dict[str, float],
        hit: bool,
        base_demand_ms: float,
        load_multiplier: float,
        n_translations: int,
        steps: List[str],
        payload: Dict[str, Any],
        wall_ms: float,
    ) -> UseCaseResult:
        """Consolida a medição de uma transação em :class:`UseCaseResult`.

        A latência combina a demanda-base do caso de uso, o tempo real de
        processamento (``wall_ms``) e o *overhead* das cinco camadas,
        ajustados por um fator de contenção dependente da carga do cenário
        (aproximação M/M/1: ``1/(1-rho)``).
        """
        total_overhead = sum(breakdown.values())

        # Fator de contenção (aproximação M/M/1): a latência cresce de
        # forma não linear com a utilização ρ = carga / saturação. ρ é
        # limitado a 0.97 para evitar divergência numérica no regime de
        # estresse, preservando a ordenação Normal < Pico < BlackFriday <
        # Estresse.
        rho = min(0.97, max(0.0, load_multiplier) / SATURATION_LOAD)
        contention = 1.0 / (1.0 - rho)

        service_ms = base_demand_ms + wall_ms + total_overhead
        latency_ms = service_ms * contention
        
        
        return UseCaseResult(
            use_case=use_case,
            success=success,
            latency_ms=latency_ms,
            layer_overhead_ms={k: (breakdown.get(k, 0.0) * contention if k == "interoperabilidade" else breakdown.get(k, 0.0))
    for k in LAYER_NAMES},
            total_overhead_ms=total_overhead,
            cache_hit=hit,
            n_translations=n_translations,
            steps=steps,
            payload=payload,
        )

    # ------------------------------------------------------------------
    # UC1 — Consultar Produto e Disponibilidade
    # ------------------------------------------------------------------
    def execute_uc1_consultar_produto(
        self,
        product_id: Optional[str] = None,
        quantity: int = 1,
        load_multiplier: float = 1.0,
    ) -> UseCaseResult:
        """Executa o **UC1 — Consultar Produto e Disponibilidade**.

        Fluxo (Schema.org, sem tradução semântica):

        #. **Comunicação**: o cliente envia ``QUERY_REF`` ao Agente de Vendas.
        #. **Orquestração**: o orquestrador roteia a consulta a ``role:sales``.
        #. **Aplicação**: o Agente de Vendas executa ``consultar_produto`` e
           ``verificar_disponibilidade`` (Schema.org ``Product``/``Offer``).
        #. **Interoperabilidade**: validação da entidade no vocabulário.
        #. **Infraestrutura**: monitoramento/registro da transação.

        Args:
            product_id: Produto a consultar. Se ``None``, sorteia um do Olist.
            quantity: Quantidade desejada para a verificação de estoque.
            load_multiplier: Multiplicador de carga do cenário.

        Returns:
            :class:`UseCaseResult` com a entidade Schema.org e a latência.
        """
        t0 = perf_counter()
        breakdown, hit = self._sample_overhead()
        steps: List[str] = []

        if product_id is None and self.dataset is not None:
            product_id = self.dataset.get_random_product(self.rng)["product_id"]
        product_id = product_id or "PROD-DESCONHECIDO"

        # 1. Comunicação — consulta FIPA-ACL QUERY_REF
        consulta = ACLMessage(
            performative=Performative.QUERY_REF,
            sender="cliente",
            receiver="role:sales",
            content={"product_id": product_id, "quantity": quantity},
            conversation_id=f"uc1-{product_id}",
            protocol="fipa-query",
            ontology="schema.org",
        )
        steps.append(f"QUERY_REF cliente -> {consulta.receiver} ({product_id})")

        # 2. Orquestração — roteamento ao agente de vendas
        decisao = self.orchestrator.route(consulta)
        if not decisao.accepted:
            wall_ms = (perf_counter() - t0) * 1000.0
            steps.append(f"REFUSE roteamento: {decisao.reason}")
            return self._finalize(
                "uc1", False, breakdown, hit, BASE_DEMAND_MS["uc1"],
                load_multiplier, 0, steps, {"motivo": decisao.reason}, wall_ms,
            )
        steps.append(f"ROUTE -> {decisao.target}")

        # 3. Aplicação — comportamentos do Agente de Vendas (Schema.org)
        resultado = self.sales.consultar_produto(product_id)
        disponivel = self.sales.verificar_disponibilidade(product_id, quantity)
        resultado["inStock"] = disponivel

        # 4. Interoperabilidade — validação no vocabulário Schema.org
        valido = self.mediator.validate(resultado["product"])
        steps.append(
            f"INFORM {decisao.target} -> cliente "
            f"(Product valido={valido}, inStock={disponivel})"
        )

        wall_ms = (perf_counter() - t0) * 1000.0
        return self._finalize(
            "uc1", True, breakdown, hit, BASE_DEMAND_MS["uc1"],
            load_multiplier, 0, steps, resultado, wall_ms,
        )

    # ------------------------------------------------------------------
    # UC2 — Calcular Prazo e Frete (com tradução semântica)
    # ------------------------------------------------------------------
    def execute_uc2_calcular_entrega(
        self,
        seller_zip: Optional[int] = None,
        customer_zip: Optional[int] = None,
        peso_kg: float = 1.0,
        modalidade: str = "standard",
        pedido_id: str = "uc2-pedido",
        load_multiplier: float = 1.0,
    ) -> UseCaseResult:
        """Executa o **UC2 — Calcular Prazo e Frete** (tradução semântica).

        Fluxo com **mediação semântica bidirecional**:

        #. **Aplicação (Vendas)**: monta a requisição de entrega em
           **Schema.org** (``ParcelDelivery`` com origem/destino/peso).
        #. **Comunicação**: ``REQUEST`` enviado ao barramento.
        #. **Orquestração**: roteamento a ``role:logistics``.
        #. **Interoperabilidade**: mediador traduz **Schema.org →
           GoodRelations** (requisição).
        #. **Aplicação (Logística)**: ``calcular_prazo`` + ``calcular_frete``;
           resposta em **GoodRelations** (``UnitPriceSpecification`` +
           ``DeliveryMethod``).
        #. **Interoperabilidade**: mediador traduz **GoodRelations →
           Schema.org** (resposta).
        #. **Orquestração/Comunicação**: ``INFORM`` devolvido ao Vendas.

        Args:
            seller_zip: CEP de origem (vendedor). Sorteado se ``None``.
            customer_zip: CEP de destino (cliente). Sorteado se ``None``.
            peso_kg: Peso da encomenda (kg).
            modalidade: ``economy`` | ``standard`` | ``express``.
            pedido_id: Identificador do pedido/conversa.
            load_multiplier: Multiplicador de carga do cenário.

        Returns:
            :class:`UseCaseResult` com prazo, frete e detalhes da tradução.
        """
        t0 = perf_counter()
        breakdown, hit = self._sample_overhead()
        steps: List[str] = []
        n_trad = 0

        # Dados reais do Olist quando os CEPs não são informados
        if (seller_zip is None or customer_zip is None) and self.dataset is not None:
            pedido = self.dataset.get_random_order(self.rng)
            seller_zip = seller_zip if seller_zip is not None else pedido["seller_zip"]
            customer_zip = (
                customer_zip if customer_zip is not None else pedido["customer_zip"]
            )
            if peso_kg <= 1.0:
                peso_kg = max(0.1, pedido.get("total_weight_kg", 1.0))

        # 1. Aplicação (Vendas) — requisição em Schema.org
        req_schema = {
            "@type": "ParcelDelivery",
            "orderNumber": pedido_id,
            "origin": seller_zip,
            "destination": customer_zip,
            "weight": {
                "@type": "QuantitativeValue",
                "value": peso_kg,
                "unitCode": "KGM",
            },
        }
        msg_req = ACLMessage(
            performative=Performative.REQUEST,
            sender=self.sales.agent_id,
            receiver="role:logistics",
            content=req_schema,
            conversation_id=pedido_id,
            protocol="fipa-request",
            ontology="schema.org",
        )
        steps.append(
            f"REQUEST {self.sales.agent_id} -> role:logistics "
            f"(Schema.org ParcelDelivery)"
        )

        # 2. Orquestração — roteamento à logística
        decisao = self.orchestrator.route(msg_req)
        if not decisao.accepted:
            wall_ms = (perf_counter() - t0) * 1000.0
            steps.append(f"REFUSE roteamento: {decisao.reason}")
            return self._finalize(
                "uc2", False, breakdown, hit, BASE_DEMAND_MS["uc2"],
                load_multiplier, n_trad, steps, {"motivo": decisao.reason}, wall_ms,
            )
        steps.append(f"ROUTE -> {decisao.target}")

        # 3. Interoperabilidade — tradução Schema.org -> GoodRelations
        req_gr = self.mediator.translate(req_schema, "goodrelations")
        n_trad += 1
        steps.append("TRANSLATE Schema.org -> GoodRelations (requisição)")

        # 4. Aplicação (Logística) — cálculo de prazo e frete (GoodRelations)
        distancia = self.logistics._distancia(seller_zip, customer_zip)
        prazo = self.logistics.calcular_prazo(
            seller_zip, customer_zip, peso=peso_kg, modalidade=modalidade
        )
        frete = self.logistics.calcular_frete(distancia, peso_kg, modalidade=modalidade)

        msg_inform = self.logistics.notificar_status(
            pedido_id, status="Cotado", prazo_dias=prazo, valor_frete=frete,
            receiver="role:sales",
        )
        resp_gr = msg_inform.content
        steps.append(
            f"INFORM role:logistics -> role:sales "
            f"(GoodRelations prazo={prazo}d frete=R${frete:.2f})"
        )

        # 5. Interoperabilidade — tradução GoodRelations -> Schema.org
        resp_schema = self.mediator.translate(resp_gr, "schema.org")
        n_trad += 1
        steps.append("TRANSLATE GoodRelations -> Schema.org (resposta)")

        payload = {
            "prazo_dias": prazo,
            "valor_frete": frete,
            "distancia_km": round(distancia, 1),
            "modalidade": modalidade,
            "request_schema_org": req_schema,
            "request_goodrelations": req_gr,
            "response_goodrelations": resp_gr,
            "response_schema_org": resp_schema,
        }
        wall_ms = (perf_counter() - t0) * 1000.0
        return self._finalize(
            "uc2", True, breakdown, hit, BASE_DEMAND_MS["uc2"],
            load_multiplier, n_trad, steps, payload, wall_ms,
        )

    # ------------------------------------------------------------------
    # UC3 — Processar Pedido (ponta a ponta)
    # ------------------------------------------------------------------
    def execute_uc3_processar_pedido(
        self,
        pedido_data: Optional[Dict[str, Any]] = None,
        modalidade: str = "standard",
        load_multiplier: float = 1.0,
    ) -> UseCaseResult:
        """Executa o **UC3 — Processar Pedido** (ponta a ponta).

        Integra os comportamentos das duas pontas e a tradução semântica:

        #. **Aplicação (Vendas)**: ``verificar_disponibilidade`` dos itens e
           ``processar_pedido`` (registra o pedido em Schema.org e gera o
           ``REQUEST`` de entrega).
        #. **Orquestração**: roteamento do ``REQUEST`` a ``role:logistics``.
        #. **Interoperabilidade**: tradução Schema.org → GoodRelations.
        #. **Aplicação (Logística)**: ``calcular_prazo`` + ``calcular_frete``;
           ``registrar_entrega``; ``notificar_status`` (INFORM GoodRelations).
        #. **Interoperabilidade**: tradução GoodRelations → Schema.org.
        #. **Aplicação (Vendas)**: ``atualizar_status`` e ``confirmar_pedido``.

        Args:
            pedido_data: Dados do pedido. Se ``None``, sorteia um do Olist.
            modalidade: Modalidade de entrega.
            load_multiplier: Multiplicador de carga do cenário.

        Returns:
            :class:`UseCaseResult` com o pedido confirmado, prazo e frete.
        """
        t0 = perf_counter()
        breakdown, hit = self._sample_overhead()
        steps: List[str] = []
        n_trad = 0

        if pedido_data is None and self.dataset is not None:
            pedido_data = self.dataset.get_random_order(self.rng)
        if pedido_data is None:
            wall_ms = (perf_counter() - t0) * 1000.0
            steps.append("FAILURE pedido indisponível (sem dataset)")
            return self._finalize(
                "uc3", True, breakdown, hit, BASE_DEMAND_MS["uc3"],
                load_multiplier, n_trad, steps, {}, wall_ms,
            )

        # 1. Aplicação (Vendas) — disponibilidade dos itens do pedido
        itens = pedido_data.get("items", [])
        for item in itens:
            pid = item.get("product_id")
            if pid and not self.sales.verificar_disponibilidade(pid, 1):
                wall_ms = (perf_counter() - t0) * 1000.0
                steps.append(f"REFUSE produto {pid} indisponível")
                return self._finalize(
                    "uc3", True, breakdown, hit, BASE_DEMAND_MS["uc3"],
                    load_multiplier, n_trad, steps,
                    {"motivo": f"produto {pid} indisponível"}, wall_ms,
                )

        # 2. Aplicação (Vendas) — registro do pedido + REQUEST de entrega
        proc = self.sales.processar_pedido(pedido_data)
        if not proc.get("valido"):
            wall_ms = (perf_counter() - t0) * 1000.0
            steps.append(f"REFUSE pedido inválido: {proc.get('erros')}")
            return self._finalize(
                "uc3", False, breakdown, hit, BASE_DEMAND_MS["uc3"],
                load_multiplier, n_trad, steps, proc, wall_ms,
            )
        pedido_id = proc["pedido_id"]
        msg_req = proc["mensagem"]
        steps.append(
            f"REQUEST {self.sales.agent_id} -> role:logistics "
            f"(pedido {pedido_id}, Schema.org)"
        )

        # 3. Orquestração — roteamento à logística
        decisao = self.orchestrator.route(msg_req)
        if not decisao.accepted:
            wall_ms = (perf_counter() - t0) * 1000.0
            steps.append(f"REFUSE roteamento: {decisao.reason}")
            return self._finalize(
                "uc3", False, breakdown, hit, BASE_DEMAND_MS["uc3"],
                load_multiplier, n_trad, steps, {"motivo": decisao.reason}, wall_ms,
            )
        steps.append(f"ROUTE -> {decisao.target}")

        # 4. Interoperabilidade — tradução Schema.org -> GoodRelations
        req_gr = self.mediator.translate(msg_req.content, "goodrelations")
        n_trad += 1
        steps.append("TRANSLATE Schema.org -> GoodRelations (requisição)")

        # 5. Aplicação (Logística) — cálculo + registro + notificação
        seller_zip = pedido_data.get("seller_zip")
        customer_zip = pedido_data.get("customer_zip")
        peso_kg = max(0.1, pedido_data.get("total_weight_kg", 1.0))
        distancia = self.logistics._distancia(seller_zip, customer_zip)
        prazo = self.logistics.calcular_prazo(
            seller_zip, customer_zip, peso=peso_kg, modalidade=modalidade
        )
        frete = self.logistics.calcular_frete(distancia, peso_kg, modalidade=modalidade)
        entrega_id = self.logistics.registrar_entrega(
            pedido_id, prazo, frete, modalidade=modalidade
        )
        msg_inform = self.logistics.notificar_status(
            pedido_id, status="Cotado", prazo_dias=prazo, valor_frete=frete,
            receiver="role:sales",
        )
        steps.append(
            f"INFORM role:logistics -> role:sales "
            f"(GoodRelations prazo={prazo}d frete=R${frete:.2f})"
        )

        # 6. Interoperabilidade — tradução GoodRelations -> Schema.org
        resp_schema = self.mediator.translate(msg_inform.content, "schema.org")
        n_trad += 1
        steps.append("TRANSLATE GoodRelations -> Schema.org (resposta)")

        # 7. Aplicação (Vendas) — atualização e confirmação do pedido
        status_info = {
            "estimatedDays": prazo,
            "shippingCost": frete,
            "orderStatus": "OrderConfirmed",
        }
        self.sales.atualizar_status(pedido_id, status_info)
        pedido_final = self.sales.confirmar_pedido(pedido_id)
        steps.append(f"CONFIRM pedido {pedido_id} -> {pedido_final['status']}")

        payload = {
            "pedido_id": pedido_id,
            "entrega_id": entrega_id,
            "status": pedido_final["status"],
            "prazo_dias": prazo,
            "valor_frete": frete,
            "distancia_km": round(distancia, 1),
            "n_itens": len(itens),
        }
        wall_ms = (perf_counter() - t0) * 1000.0
        return self._finalize(
            "uc3", True, breakdown, hit, BASE_DEMAND_MS["uc3"],
            load_multiplier, n_trad, steps, payload, wall_ms,
        )

    # ------------------------------------------------------------------
    def execute(
        self, use_case: str, load_multiplier: float = 1.0, **kwargs: Any
    ) -> UseCaseResult:
        """Despacha a execução pelo identificador do caso de uso.

        Args:
            use_case: ``uc1`` | ``uc2`` | ``uc3``.
            load_multiplier: Multiplicador de carga do cenário.
            **kwargs: Parâmetros específicos do caso de uso.

        Returns:
            :class:`UseCaseResult` do caso de uso executado.
        """
        uc = use_case.lower().strip()
        if uc == "uc1":
            return self.execute_uc1_consultar_produto(
                load_multiplier=load_multiplier, **kwargs
            )
        if uc == "uc2":
            return self.execute_uc2_calcular_entrega(
                load_multiplier=load_multiplier, **kwargs
            )
        if uc == "uc3":
            return self.execute_uc3_processar_pedido(
                load_multiplier=load_multiplier, **kwargs
            )
        raise ValueError(f"Caso de uso desconhecido: {use_case!r}")
