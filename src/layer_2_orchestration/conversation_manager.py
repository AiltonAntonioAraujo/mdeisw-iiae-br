"""Conversation Manager — Camada 2 (Orquestração) do IIAE-BR.

Acompanha o ciclo de vida das **conversas** entre agentes, indexadas
pelo ``conversation_id``. Controla o estado de cada conversa (aberta,
aguardando, concluída, expirada), aplica *timeout* às conversas inativas
e mantém um histórico das mensagens trocadas, oferecendo à orquestração
uma visão consolidada das interações em andamento.

Diferencia-se do :class:`ContextManager` da camada 3: enquanto aquele
foca no *contexto semântico* (vocabulários, necessidade de tradução),
este foca na *gestão operacional* das conversas (estado, timeout, SLA).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from src.layer_5_infrastructure.logging_service import get_logger

logger = get_logger(__name__)


class ConversationState(str, Enum):
    OPEN = "open"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class Conversation:
    """Representa uma conversa gerenciada."""

    conversation_id: str
    initiator: str
    protocol: str = ""
    state: ConversationState = ConversationState.OPEN
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    messages: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.last_activity - self.created_at


class ConversationManager:
    """Gerencia conversas, estados e timeouts."""

    def __init__(self, timeout_s: float = 30.0, max_messages: int = 100) -> None:
        self.timeout_s = timeout_s
        self.max_messages = max_messages
        self._conversations: Dict[str, Conversation] = {}
        self.completed = 0
        self.expired = 0

    # ------------------------------------------------------------------
    def open(
        self, conversation_id: str, initiator: str, protocol: str = ""
    ) -> Conversation:
        conv = self._conversations.get(conversation_id)
        if conv is None:
            conv = Conversation(conversation_id, initiator, protocol)
            self._conversations[conversation_id] = conv
        return conv

    def record(
        self,
        conversation_id: str,
        sender: str,
        performative: str,
        initiator: str = "",
        protocol: str = "",
    ) -> Conversation:
        """Registra uma mensagem na conversa, atualizando o estado."""
        conv = self.open(conversation_id, initiator or sender, protocol)
        conv.last_activity = time.time()
        conv.messages.append({
            "t": conv.last_activity,
            "sender": sender,
            "performative": performative,
        })
        if len(conv.messages) > self.max_messages:
            conv.messages = conv.messages[-self.max_messages:]

        # Atualiza estado conforme performativa terminal
        p = performative.lower()
        if p in ("inform", "confirm"):
            conv.state = ConversationState.COMPLETED
            self.completed += 1
        elif p in ("failure", "refuse", "reject-proposal", "not-understood"):
            conv.state = ConversationState.FAILED
        else:
            conv.state = ConversationState.WAITING
        return conv

    # ------------------------------------------------------------------
    def sweep_timeouts(self, now: Optional[float] = None) -> int:
        """Expira conversas inativas além do timeout. Retorna nº expiradas."""
        now = now if now is not None else time.time()
        count = 0
        for conv in self._conversations.values():
            if conv.state in (ConversationState.OPEN, ConversationState.WAITING):
                if now - conv.last_activity > self.timeout_s:
                    conv.state = ConversationState.EXPIRED
                    self.expired += 1
                    count += 1
        return count

    def get(self, conversation_id: str) -> Optional[Conversation]:
        return self._conversations.get(conversation_id)

    def active(self) -> List[Conversation]:
        return [
            c for c in self._conversations.values()
            if c.state in (ConversationState.OPEN, ConversationState.WAITING)
        ]

    def summary(self) -> Dict[str, int]:
        return {
            "total": len(self._conversations),
            "active": len(self.active()),
            "completed": self.completed,
            "expired": self.expired,
        }
