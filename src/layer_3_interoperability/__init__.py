"""Camada 3 — Interoperabilidade do IIAE-BR (camada CENTRAL).

Coração da arquitetura: adapta o protocolo FIPA-ACL, realiza a mediação
semântica entre Schema.org e GoodRelations, gerencia identidades,
contextos conversacionais e o diretório de agentes.

Subpacotes:
    * :mod:`~src.layer_3_interoperability.protocol_adapter`
    * :mod:`~src.layer_3_interoperability.semantic_mediator`
"""

from src.layer_3_interoperability.agent_registry import (
    AgentDescriptor,
    AgentRegistry,
)
from src.layer_3_interoperability.context_manager import (
    ContextManager,
    ConversationContext,
)
from src.layer_3_interoperability.identity_manager import (
    AgentIdentity,
    IdentityManager,
)

__all__ = [
    "AgentDescriptor",
    "AgentRegistry",
    "ContextManager",
    "ConversationContext",
    "AgentIdentity",
    "IdentityManager",
]
