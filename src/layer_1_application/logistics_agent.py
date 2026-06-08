"""Logistics Agent — Camada 1 (Aplicação) do IIAE-BR.

Agente de **logística** (transportadora / operador de entrega). Fala
exclusivamente o vocabulário **GoodRelations** (``BusinessEntity``,
``ProductOrService``, ``Offering``, ``UnitPriceSpecification``,
``DeliveryMethod``). Implementa quatro comportamentos (*behaviours*)
conforme o estudo de caso (seção 3.3):

* ``CalcularPrazoBehaviour`` (:meth:`calcular_prazo`) — recebe
  solicitações de cálculo de prazo, analisa origem/destino e estima o
  tempo de entrega com base em dados históricos do Olist;
* ``CalcularFreteBehaviour`` (:meth:`calcular_frete`) — calcula o custo
  de frete a partir de distância, peso e modalidade;
* ``RastrearEntregaBehaviour`` (:meth:`rastrear_entrega`) — monitora e
  reporta o status de entregas em andamento;
* ``NotificarStatusBehaviour`` (:meth:`notificar_status`) — envia
  atualizações de status ao Agente de Vendas (FIPA-ACL INFORM).

Não conhece o vocabulário Schema.org: a tradução entre o agente de
vendas (Schema.org) e este agente (GoodRelations) é realizada pela
camada 3 (Mediador Semântico).
"""

from __future__ import annotations

import random
from typing import Any, Dict, Optional

from src.layer_5_infrastructure.logging_service import get_logger
from src.utils.fipa_acl import ACLMessage, Performative

logger = get_logger(__name__)

VOCABULARY = "goodrelations"

# Modalidades de entrega e seus multiplicadores de custo/prazo
MODALIDADES = {
    "economy": {"custo": 0.85, "prazo": 1.40},
    "standard": {"custo": 1.00, "prazo": 1.00},
    "express": {"custo": 1.80, "prazo": 0.55},
}


class LogisticsAgent:
    """Agente de logística baseado em GoodRelations.

    Parameters:
        agent_id: Identificador único do agente.
        dataset_olist: Instância de ``OlistDataset`` para geolocalização e
            dados históricos de entrega. Opcional.
        base_cost: Custo-base de frete (BRL).
        cost_per_kg: Custo por quilograma (BRL/kg).
        cost_per_km: Custo por quilômetro (BRL/km).
        rng: Gerador aleatório para reprodutibilidade.
    """

    role = "logistics"
    vocabulary = VOCABULARY

    def __init__(
        self,
        agent_id: str,
        dataset_olist: Any = None,
        base_cost: float = 15.0,
        cost_per_kg: float = 2.5,
        cost_per_km: float = 0.05,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.agent_id = agent_id
        self.dataset = dataset_olist
        self.ontology = "goodrelations"
        self.base_cost = base_cost
        self.cost_per_kg = cost_per_kg
        self.cost_per_km = cost_per_km
        self.rng = rng or random.Random()
        self.handled = 0
        # Rastreamento de entregas (entrega_id -> estado)
        self.entregas: Dict[str, Dict[str, Any]] = {}
        self._delivery_counter = 0

    # ------------------------------------------------------------------
    # Construção de entidades GoodRelations
    # ------------------------------------------------------------------
    def build_business_entity(self) -> Dict[str, Any]:
        """Constrói uma entidade ``gr:BusinessEntity``."""
        return {
            "@type": "BusinessEntity",
            "legalName": f"Transportadora {self.agent_id}",
            "name": self.agent_id,
        }

    def build_price_spec(self, value: float, currency: str = "BRL") -> Dict[str, Any]:
        """Constrói uma ``gr:UnitPriceSpecification`` (custo de frete)."""
        return {
            "@type": "UnitPriceSpecification",
            "hasCurrencyValue": round(value, 2),
            "hasCurrency": currency,
        }

    def build_delivery_method(self, days: int) -> Dict[str, Any]:
        """Constrói uma ``gr:DeliveryMethod`` com prazo estimado."""
        return {
            "@type": "DeliveryMethod",
            "availableDeliveryMethod": "gr:DeliveryModeParcelService",
            "durationOfWarrantyInMonths": days,  # reutilizado como prazo (dias)
        }

    # ------------------------------------------------------------------
    # Cálculo de frete
    # ------------------------------------------------------------------
    def quote(self, weight_kg: float, distance_km: float) -> Dict[str, Any]:
        """Calcula o frete e retorna entidades GoodRelations."""
        cost = (
            self.base_cost
            + weight_kg * self.cost_per_kg
            + distance_km * self.cost_per_km
        )
        days = max(1, int(distance_km / 400) + self.rng.randint(1, 3))
        return {
            "priceSpecification": self.build_price_spec(cost),
            "deliveryMethod": self.build_delivery_method(days),
            "estimatedDays": days,
        }

    # ------------------------------------------------------------------
    # Comportamentos FIPA-ACL
    # ------------------------------------------------------------------
    def handle(self, msg: ACLMessage) -> Optional[ACLMessage]:
        """Processa uma mensagem recebida e devolve a resposta FIPA-ACL."""
        self.handled += 1
        p = msg.performative

        if p == Performative.REQUEST:
            return self._handle_request(msg)
        if p in (Performative.QUERY_IF, Performative.QUERY_REF):
            return self._handle_query(msg)
        if p == Performative.AGREE:
            return None  # aguardando execução
        return msg.create_reply(Performative.NOT_UNDERSTOOD)

    def _handle_request(self, msg: ACLMessage) -> ACLMessage:
        content = msg.content or {}
        weight = float(content.get("weight_kg", 1.0))
        distance = float(content.get("distance_km", 100.0))
        quote = self.quote(weight, distance)
        # Responde diretamente com inform (fluxo simplificado request->inform)
        return msg.create_reply(Performative.INFORM, content=quote)

    def _handle_query(self, msg: ACLMessage) -> ACLMessage:
        content = msg.content or {}
        distance = float(content.get("distance_km", 100.0))
        days = max(1, int(distance / 400) + self.rng.randint(1, 3))
        return msg.create_reply(
            Performative.INFORM,
            content={"deliveryMethod": self.build_delivery_method(days)},
        )

    # ==================================================================
    # Comportamentos do estudo de caso (seção 3.3)
    # ==================================================================

    # COMPORTAMENTO 1 — CalcularPrazoBehaviour --------------------------
    def calcular_prazo(
        self,
        origem: Optional[int],
        destino: Optional[int],
        peso: float = 1.0,
        modalidade: str = "standard",
    ) -> int:
        """Estima o prazo de entrega (dias) entre origem e destino.

        Analisa a distância entre os CEPs (via geolocalização do Olist) e
        estima o tempo de entrega combinando uma parcela fixa de manuseio
        com uma parcela proporcional à distância e ao peso. A modalidade
        ajusta o prazo (``express`` mais rápido, ``economy`` mais lento).

        Args:
            origem: Prefixo de CEP do vendedor (origem).
            destino: Prefixo de CEP do cliente (destino).
            peso: Peso da encomenda (kg).
            modalidade: ``economy`` | ``standard`` | ``express``.

        Returns:
            Prazo estimado em dias (inteiro, mínimo 1).
        """
        distancia = self._distancia(origem, destino)
        fator = MODALIDADES.get(modalidade, MODALIDADES["standard"])["prazo"]

        # Manuseio (1-2 dias) + trânsito (~700 km/dia) + acréscimo por peso
        manuseio = 1.0 + min(1.0, peso / 30.0)
        transito = distancia / 700.0
        prazo = (manuseio + transito) * fator
        # Variabilidade realista (±1 dia)
        prazo += self.rng.uniform(-0.5, 1.0)
        return max(1, int(round(prazo)))

    def _distancia(self, origem: Optional[int], destino: Optional[int]) -> float:
        """Distância (km) entre dois CEPs, usando o dataset quando disponível."""
        if self.dataset is not None:
            return self.dataset.calculate_distance(origem, destino)
        # Sem dataset: distância sintética média
        return 600.0

    # COMPORTAMENTO 2 — CalcularFreteBehaviour --------------------------
    def calcular_frete(
        self,
        distancia_km: float,
        peso_kg: float,
        modalidade: str = "standard",
    ) -> float:
        """Calcula o custo de frete (BRL).

        Fórmula: ``base + (distância × taxa_km) + (peso × taxa_kg)``,
        ajustada pelo multiplicador de custo da modalidade.

        Args:
            distancia_km: Distância da entrega (km).
            peso_kg: Peso da encomenda (kg).
            modalidade: ``economy`` | ``standard`` | ``express``.

        Returns:
            Valor do frete em BRL (arredondado a 2 casas).
        """
        fator = MODALIDADES.get(modalidade, MODALIDADES["standard"])["custo"]
        custo = (
            self.base_cost
            + distancia_km * self.cost_per_km
            + peso_kg * self.cost_per_kg
        ) * fator
        return round(max(0.0, custo), 2)

    # COMPORTAMENTO 3 — RastrearEntregaBehaviour ------------------------
    def registrar_entrega(
        self,
        pedido_id: str,
        prazo_dias: int,
        valor_frete: float,
        modalidade: str = "standard",
    ) -> str:
        """Registra uma entrega em andamento e retorna seu ``entrega_id``."""
        self._delivery_counter += 1
        entrega_id = f"{self.agent_id}-ENT-{self._delivery_counter:06d}"
        self.entregas[entrega_id] = {
            "entrega_id": entrega_id,
            "pedido_id": pedido_id,
            "prazo_dias": prazo_dias,
            "valor_frete": valor_frete,
            "modalidade": modalidade,
            "status": "PostagemPendente",
            "progresso": 0.0,
        }
        return entrega_id

    def rastrear_entrega(self, entrega_id: str) -> Dict[str, Any]:
        """Monitora e reporta o status de uma entrega em andamento.

        Args:
            entrega_id: Identificador da entrega.

        Returns:
            Dicionário com ``status``, ``localizacao`` atual e ``previsao``
            (dias restantes). Para entregas desconhecidas, retorna
            ``status="NaoEncontrada"``.
        """
        entrega = self.entregas.get(entrega_id)
        if entrega is None:
            return {"entrega_id": entrega_id, "status": "NaoEncontrada"}

        # Avança o progresso da entrega de forma incremental
        entrega["progresso"] = min(1.0, entrega["progresso"] + self.rng.uniform(0.1, 0.4))
        progresso = entrega["progresso"]
        if progresso >= 1.0:
            status, local = "Entregue", "Destino"
        elif progresso >= 0.6:
            status, local = "EmRota", "CentroDistribuicaoDestino"
        elif progresso >= 0.2:
            status, local = "EmTransito", "CentroDistribuicaoOrigem"
        else:
            status, local = "Postado", "Origem"
        entrega["status"] = status

        previsao = max(0, int(round(entrega["prazo_dias"] * (1.0 - progresso))))
        return {
            "entrega_id": entrega_id,
            "pedido_id": entrega["pedido_id"],
            "status": status,
            "localizacao": local,
            "previsao_dias": previsao,
            "progresso": round(progresso, 2),
        }

    # COMPORTAMENTO 4 — NotificarStatusBehaviour ------------------------
    def notificar_status(
        self,
        pedido_id: str,
        status: str,
        prazo_dias: Optional[int] = None,
        valor_frete: Optional[float] = None,
        receiver: str = "role:sales",
    ) -> ACLMessage:
        """Cria uma mensagem FIPA-ACL INFORM para o Agente de Vendas.

        O conteúdo é expresso em **GoodRelations** (custo via
        ``UnitPriceSpecification`` e prazo via ``DeliveryMethod``); a camada
        3 traduz para Schema.org antes de chegar ao agente de vendas.

        Args:
            pedido_id: Identificador do pedido.
            status: Novo status logístico (ex.: ``EmRota``, ``Entregue``).
            prazo_dias: Prazo estimado (dias), se aplicável.
            valor_frete: Valor do frete (BRL), se aplicável.
            receiver: Destinatário (papel ou id). Padrão ``role:sales``.

        Returns:
            A mensagem :class:`ACLMessage` INFORM pronta para envio.
        """
        conteudo: Dict[str, Any] = {
            "@type": "Offering",
            "hasBusinessFunction": status,
            "orderNumber": pedido_id,
        }
        if valor_frete is not None:
            conteudo["priceSpecification"] = self.build_price_spec(valor_frete)
        if prazo_dias is not None:
            conteudo["deliveryMethod"] = self.build_delivery_method(prazo_dias)

        return ACLMessage(
            performative=Performative.INFORM,
            sender=self.agent_id,
            receiver=receiver,
            content=conteudo,
            conversation_id=pedido_id,
            protocol="fipa-request",
            ontology="goodrelations",
        )
