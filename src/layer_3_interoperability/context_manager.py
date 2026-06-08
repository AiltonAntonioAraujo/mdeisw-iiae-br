"""Context Manager — Camada 3 (Interoperabilidade) do IIAE-BR.

Mantém o **contexto conversacional** das interações entre agentes,
indexado pelo ``conversation_id`` das mensagens FIPA-ACL. Cada contexto
armazena o protocolo em uso, o vocabulário de cada participante, o
estado corrente e um histórico resumido das mensagens, permitindo que a
camada de interoperabilidade e a de orquestração tomem decisões de
roteamento e mediação coerentes ao longo de uma conversa.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.layer_5_infrastructure.logging_service import get_logger

logger = get_logger(__name__)


@dataclass
class ConversationContext:
    """Contexto de uma conversa entre agentes."""

    conversation_id: str
    protocol: str = ""
    participants: Dict[str, str] = field(default_factory=dict)  # aid -> vocab
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    turns: int = 0
    history: List[Dict[str, Any]] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = time.time()
        self.turns += 1


class ContextManager:
    """Gerencia contextos conversacionais por ``conversation_id``."""

    def __init__(self, max_history: int = 50) -> None:
        self._contexts: Dict[str, ConversationContext] = {}
        self.max_history = max_history

    # ------------------------------------------------------------------
    def get_or_create(
        self, conversation_id: str, protocol: str = ""
    ) -> ConversationContext:
        ctx = self._contexts.get(conversation_id)
        if ctx is None:
            ctx = ConversationContext(conversation_id, protocol=protocol)
            self._contexts[conversation_id] = ctx
        return ctx

    def update(
        self,
        conversation_id: str,
        sender: str = "",
        receiver: str = "",
        performative: str = "",
        sender_vocab: str = "",
        receiver_vocab: str = "",
        protocol: str = "",
    ) -> ConversationContext:
        """Atualiza o contexto a partir de uma mensagem trocada."""
        ctx = self.get_or_create(conversation_id, protocol)
        if protocol and not ctx.protocol:
            ctx.protocol = protocol
        if sender and sender_vocab:
            ctx.participants[sender] = sender_vocab
        if receiver and receiver_vocab:
            ctx.participants[receiver] = receiver_vocab
        ctx.touch()
        ctx.history.append({
            "t": ctx.updated_at,
            "sender": sender,
            "receiver": receiver,
            "performative": performative,
        })
        if len(ctx.history) > self.max_history:
            ctx.history = ctx.history[-self.max_history:]
        return ctx

    # ------------------------------------------------------------------
    def needs_translation(self, conversation_id: str) -> bool:
        """Indica se os participantes usam vocabulários distintos."""
        ctx = self._contexts.get(conversation_id)
        if not ctx:
            return False
        vocabs = set(ctx.participants.values())
        return len(vocabs) > 1

    def get(self, conversation_id: str) -> Optional[ConversationContext]:
        return self._contexts.get(conversation_id)

    def purge_expired(self, ttl_s: float) -> int:
        """Remove contextos inativos há mais de ``ttl_s`` segundos."""
        now = time.time()
        expired = [cid for cid, c in self._contexts.items()
                   if now - c.updated_at > ttl_s]
        for cid in expired:
            del self._contexts[cid]
        return len(expired)

    def active_count(self) -> int:
        return len(self._contexts)
