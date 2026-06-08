"""Orchestrator — Camada 2 (Orquestração) do IIAE-BR.

Componente **central** da camada de orquestração. Coordena o roteamento
inteligente de mensagens entre agentes, integrando:

#. :class:`AgentRegistry` (camada 3) — descoberta do agente de destino;
#. :class:`LoadBalancer` — escolha da instância do papel;
#. :class:`ConversationManager` — gestão do ciclo de vida das conversas;
#. :class:`WorkflowCoordinator` — coordenação de fluxos multi-etapas;
#. :class:`SecurityGateway` (camada 5) — política básica de segurança.

Mantém uma **fila de prioridade** simples (mensagens de fechamento de
pedido têm prioridade sobre consultas) e expõe métricas de roteamento.
"""

from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.layer_2_orchestration.conversation_manager import ConversationManager
from src.layer_2_orchestration.load_balancer import LoadBalancer
from src.layer_2_orchestration.workflow_coordinator import WorkflowCoordinator
from src.layer_3_interoperability.agent_registry import AgentRegistry
from src.layer_5_infrastructure.logging_service import get_logger
from src.utils.fipa_acl import ACLMessage, Performative

logger = get_logger(__name__)

# Prioridade por performativa (menor = mais prioritário)
PERFORMATIVE_PRIORITY: Dict[Performative, int] = {
    Performative.ACCEPT_PROPOSAL: 0,
    Performative.AGREE: 1,
    Performative.REQUEST: 2,
    Performative.PROPOSE: 2,
    Performative.CFP: 3,
    Performative.QUERY_REF: 4,
    Performative.QUERY_IF: 4,
    Performative.INFORM: 5,
    Performative.SUBSCRIBE: 6,
}
DEFAULT_PRIORITY = 5


@dataclass(order=True)
class _PrioritizedMessage:
    priority: int
    seq: int
    message: ACLMessage = field(compare=False)


@dataclass
class RoutingDecision:
    """Decisão de roteamento produzida pelo orquestrador."""

    accepted: bool
    target: Optional[str] = None
    reason: str = ""


class Orchestrator:
    """Orquestrador de mensagens da camada 2."""

    def __init__(
        self,
        registry: Optional[AgentRegistry] = None,
        load_balancer: Optional[LoadBalancer] = None,
        conversation_manager: Optional[ConversationManager] = None,
        workflow_coordinator: Optional[WorkflowCoordinator] = None,
        security_gateway: Any = None,
    ) -> None:
        self.registry = registry or AgentRegistry()
        self.load_balancer = load_balancer or LoadBalancer()
        self.conversations = conversation_manager or ConversationManager()
        self.workflows = workflow_coordinator or WorkflowCoordinator()
        self.security = security_gateway
        self._queue: List[_PrioritizedMessage] = []
        self._counter = itertools.count()
        self.routed = 0
        self.blocked = 0

    # ------------------------------------------------------------------
    def enqueue(self, msg: ACLMessage) -> None:
        """Insere uma mensagem na fila de prioridade."""
        prio = PERFORMATIVE_PRIORITY.get(msg.performative, DEFAULT_PRIORITY)
        heapq.heappush(
            self._queue,
            _PrioritizedMessage(prio, next(self._counter), msg),
        )

    def dequeue(self) -> Optional[ACLMessage]:
        """Remove a mensagem de maior prioridade da fila."""
        if not self._queue:
            return None
        return heapq.heappop(self._queue).message

    def pending(self) -> int:
        return len(self._queue)

    # ------------------------------------------------------------------
    def route(self, msg: ACLMessage) -> RoutingDecision:
        """Roteia uma mensagem ao agente de destino apropriado.

        Se ``msg.receiver`` indicar um papel (ex.: ``role:logistics``),
        usa o registro + balanceador para escolher a instância concreta.
        Aplica a política de segurança, se configurada.
        """
        # Política de segurança (camada 5)
        if self.security is not None:
            allowed = self.security.authorize(msg.sender, msg.receiver,
                                               msg.performative.value)
            if not allowed:
                self.blocked += 1
                return RoutingDecision(False, None, "bloqueado pela seguranca")

        # Atualiza gestão de conversa
        self.conversations.record(
            msg.conversation_id, msg.sender, msg.performative.value,
            protocol=msg.protocol,
        )

        target = self._resolve_target(msg.receiver)
        if target is None:
            return RoutingDecision(False, None, "destino nao encontrado")

        self.routed += 1
        return RoutingDecision(True, target, "ok")

    def _resolve_target(self, receiver: str) -> Optional[str]:
        """Resolve o destino: papel -> instância via balanceador."""
        if receiver.startswith("role:"):
            role = receiver.split(":", 1)[1]
            candidates = self.registry.find_by_role(role)
            if not candidates:
                return None
            # garante pool no balanceador (apenas se mudou, para preservar
            # o estado round-robin entre chamadas)
            current = self.load_balancer._pools.get(role)
            desired = [c.aid for c in candidates]
            if current != desired:
                self.load_balancer.register_pool(role, desired)
            return self.load_balancer.select(role)
        # destino direto
        return receiver

    # ------------------------------------------------------------------
    def summary(self) -> Dict[str, Any]:
        return {
            "routed": self.routed,
            "blocked": self.blocked,
            "pending": self.pending(),
            "conversations": self.conversations.summary(),
            "load_balancer": self.load_balancer.summary(),
            "workflows": self.workflows.summary(),
        }
