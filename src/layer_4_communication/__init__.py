"""Camada 4 — Comunicação do IIAE-BR.

Transporte de mensagens entre agentes: barramento de mensagens, serialização
JSON-LD, adaptador de transporte FIPA-ACL e gerência de conexões.
"""

from src.layer_4_communication.connection_manager import (
    Connection,
    ConnectionManager,
)
from src.layer_4_communication.fipa_adapter import FIPACommunicationAdapter
from src.layer_4_communication.message_bus import CommunicationMessageBus
from src.layer_4_communication.serialization import (
    DEFAULT_CONTEXT,
    JSONLDSerializer,
)

__all__ = [
    "Connection",
    "ConnectionManager",
    "FIPACommunicationAdapter",
    "CommunicationMessageBus",
    "DEFAULT_CONTEXT",
    "JSONLDSerializer",
]
