"""Protocol Adapter — Camada 3 (Interoperabilidade) do IIAE-BR.

Adaptação do protocolo FIPA-ACL: análise/validação de mensagens,
mapeamento de performativas, máquinas de estado dos protocolos de
interação (Request, Query, Contract-Net, Subscribe) e serialização JSON-LD.
"""

from src.layer_3_interoperability.protocol_adapter.fipa_acl_adapter import (
    AdaptationResult,
    FIPAACLAdapter,
)
from src.layer_3_interoperability.protocol_adapter.interaction_protocol import (
    InteractionProtocolEngine,
    ProtocolInstance,
    ProtocolState,
)
from src.layer_3_interoperability.protocol_adapter.message_parser import (
    MessageParser,
    ParseResult,
)
from src.layer_3_interoperability.protocol_adapter.performative_mapper import (
    CommunicativeAct,
    PerformativeMapper,
)

__all__ = [
    "AdaptationResult",
    "FIPAACLAdapter",
    "InteractionProtocolEngine",
    "ProtocolInstance",
    "ProtocolState",
    "MessageParser",
    "ParseResult",
    "CommunicativeAct",
    "PerformativeMapper",
]
