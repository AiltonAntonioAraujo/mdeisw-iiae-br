"""Interaction Protocol — Camada 3 (Interoperabilidade) / Protocol Adapter.

Implementa **máquinas de estado** para os protocolos de interação FIPA-ACL
suportados pela arquitetura IIAE-BR:

* **FIPA-Request** — solicitação de execução de ação.
* **FIPA-Query** — consulta de informação (query-if / query-ref).
* **FIPA-Contract-Net** — negociação por proposta (cfp / propose / accept).
* **FIPA-Subscribe** — assinatura de notificações.

Cada máquina de estado controla as transições válidas a partir das
performativas trocadas, permitindo detectar violações de protocolo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from src.layer_5_infrastructure.logging_service import get_logger
from src.utils.fipa_acl import Performative

logger = get_logger(__name__)


class ProtocolState(str, Enum):
    """Estados genéricos de uma conversa de protocolo."""

    INITIATED = "initiated"
    PENDING = "pending"        # aguardando resposta de comprometimento
    NEGOTIATING = "negotiating"
    ACTIVE = "active"          # ação/assinatura em andamento
    COMPLETED = "completed"
    REFUSED = "refused"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Estados terminais (conversa encerrada)
TERMINAL_STATES = {
    ProtocolState.COMPLETED,
    ProtocolState.REFUSED,
    ProtocolState.FAILED,
    ProtocolState.CANCELLED,
}


# Tabelas de transição: (estado_atual, performativa) -> novo_estado
_REQUEST_FSM: Dict[Tuple[ProtocolState, Performative], ProtocolState] = {
    (ProtocolState.INITIATED, Performative.REQUEST): ProtocolState.PENDING,
    (ProtocolState.PENDING, Performative.AGREE): ProtocolState.ACTIVE,
    (ProtocolState.PENDING, Performative.REFUSE): ProtocolState.REFUSED,
    (ProtocolState.PENDING, Performative.NOT_UNDERSTOOD): ProtocolState.FAILED,
    (ProtocolState.ACTIVE, Performative.INFORM): ProtocolState.COMPLETED,
    (ProtocolState.ACTIVE, Performative.FAILURE): ProtocolState.FAILED,
}

_QUERY_FSM: Dict[Tuple[ProtocolState, Performative], ProtocolState] = {
    (ProtocolState.INITIATED, Performative.QUERY_IF): ProtocolState.PENDING,
    (ProtocolState.INITIATED, Performative.QUERY_REF): ProtocolState.PENDING,
    (ProtocolState.PENDING, Performative.INFORM): ProtocolState.COMPLETED,
    (ProtocolState.PENDING, Performative.REFUSE): ProtocolState.REFUSED,
    (ProtocolState.PENDING, Performative.FAILURE): ProtocolState.FAILED,
}

_CONTRACT_NET_FSM: Dict[Tuple[ProtocolState, Performative], ProtocolState] = {
    (ProtocolState.INITIATED, Performative.CFP): ProtocolState.NEGOTIATING,
    (ProtocolState.NEGOTIATING, Performative.PROPOSE): ProtocolState.PENDING,
    (ProtocolState.NEGOTIATING, Performative.REFUSE): ProtocolState.REFUSED,
    (ProtocolState.PENDING, Performative.ACCEPT_PROPOSAL): ProtocolState.ACTIVE,
    (ProtocolState.PENDING, Performative.REJECT_PROPOSAL): ProtocolState.REFUSED,
    (ProtocolState.ACTIVE, Performative.INFORM): ProtocolState.COMPLETED,
    (ProtocolState.ACTIVE, Performative.FAILURE): ProtocolState.FAILED,
}

_SUBSCRIBE_FSM: Dict[Tuple[ProtocolState, Performative], ProtocolState] = {
    (ProtocolState.INITIATED, Performative.SUBSCRIBE): ProtocolState.PENDING,
    (ProtocolState.PENDING, Performative.AGREE): ProtocolState.ACTIVE,
    (ProtocolState.PENDING, Performative.REFUSE): ProtocolState.REFUSED,
    (ProtocolState.ACTIVE, Performative.INFORM): ProtocolState.ACTIVE,
    (ProtocolState.ACTIVE, Performative.CANCEL): ProtocolState.CANCELLED,
}

_PROTOCOLS: Dict[str, Dict[Tuple[ProtocolState, Performative], ProtocolState]] = {
    "fipa-request": _REQUEST_FSM,
    "fipa-query": _QUERY_FSM,
    "fipa-contract-net": _CONTRACT_NET_FSM,
    "fipa-subscribe": _SUBSCRIBE_FSM,
}

# Cancelamento é permitido em qualquer estado não-terminal de qualquer protocolo
_CANCELABLE = True


@dataclass
class ProtocolInstance:
    """Instância (conversa) ativa de um protocolo de interação."""

    conversation_id: str
    protocol: str
    state: ProtocolState = ProtocolState.INITIATED
    history: List[Tuple[Performative, ProtocolState]] = field(default_factory=list)

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES


class InteractionProtocolEngine:
    """Gerencia as máquinas de estado dos protocolos de interação."""

    def __init__(self) -> None:
        self._instances: Dict[str, ProtocolInstance] = {}
        self.violations = 0

    # ------------------------------------------------------------------
    def start(self, conversation_id: str, protocol: str) -> ProtocolInstance:
        """Inicia uma nova instância de protocolo."""
        protocol = self._normalize(protocol)
        instance = ProtocolInstance(conversation_id, protocol)
        self._instances[conversation_id] = instance
        return instance

    def get(self, conversation_id: str) -> Optional[ProtocolInstance]:
        return self._instances.get(conversation_id)

    # ------------------------------------------------------------------
    def transition(
        self, conversation_id: str, performative: Performative, protocol: str = ""
    ) -> Tuple[bool, ProtocolState]:
        """Aplica uma transição de estado para uma performativa.

        Retorna ``(valido, novo_estado)``. Se a transição for inválida,
        o estado da instância é preservado e ``valido`` é ``False``.
        """
        instance = self._instances.get(conversation_id)
        if instance is None:
            instance = self.start(conversation_id, protocol or "fipa-request")

        fsm = _PROTOCOLS.get(instance.protocol, _REQUEST_FSM)

        # CANCEL encerra qualquer protocolo em estado não-terminal
        if performative == Performative.CANCEL and not instance.is_terminal:
            instance.state = ProtocolState.CANCELLED
            instance.history.append((performative, instance.state))
            return True, instance.state

        key = (instance.state, performative)
        if key in fsm:
            instance.state = fsm[key]
            instance.history.append((performative, instance.state))
            return True, instance.state

        # Transição inválida
        self.violations += 1
        logger.debug(
            "Violação de protocolo %s: %s não permitido em %s",
            instance.protocol, performative.value, instance.state.value,
        )
        return False, instance.state

    # ------------------------------------------------------------------
    @staticmethod
    def _normalize(protocol: str) -> str:
        p = (protocol or "").lower().strip()
        if p in _PROTOCOLS:
            return p
        aliases = {
            "request": "fipa-request",
            "query": "fipa-query",
            "contract-net": "fipa-contract-net",
            "contractnet": "fipa-contract-net",
            "subscribe": "fipa-subscribe",
        }
        return aliases.get(p, "fipa-request")

    def active_count(self) -> int:
        return sum(1 for i in self._instances.values() if not i.is_terminal)

    def summary(self) -> Dict[str, int]:
        return {
            "total": len(self._instances),
            "active": self.active_count(),
            "violations": self.violations,
        }
