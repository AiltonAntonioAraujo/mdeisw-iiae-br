"""FIPA-ACL Adapter — Camada 3 (Interoperabilidade) / Protocol Adapter.

Componente **principal** do adaptador de protocolo. Integra:

#. :class:`MessageParser` — análise e validação estrutural;
#. :class:`PerformativeMapper` — mapeamento de performativas / atos comunicativos;
#. :class:`InteractionProtocolEngine` — máquinas de estado dos protocolos;
#. :class:`JSONLDSerializer` — (de)serialização JSON-LD.

É o ponto único de entrada/saída de mensagens FIPA-ACL na camada de
interoperabilidade. Garante que cada mensagem seja válida, coerente com o
protocolo em curso e corretamente serializada antes de seguir para a
mediação semântica ou para a camada de comunicação.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.layer_3_interoperability.protocol_adapter.interaction_protocol import (
    InteractionProtocolEngine,
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
from src.layer_4_communication.serialization import JSONLDSerializer
from src.layer_5_infrastructure.logging_service import get_logger
from src.utils.fipa_acl import ACLMessage, Performative

logger = get_logger(__name__)


@dataclass
class AdaptationResult:
    """Resultado do processamento de uma mensagem pelo adaptador."""

    accepted: bool
    message: Optional[ACLMessage] = None
    act: Optional[CommunicativeAct] = None
    protocol_state: Optional[ProtocolState] = None
    errors: Optional[list] = None


class FIPAACLAdapter:
    """Adaptador principal de protocolo FIPA-ACL da camada 3."""

    def __init__(
        self,
        serializer: JSONLDSerializer | None = None,
        parser: MessageParser | None = None,
        mapper: PerformativeMapper | None = None,
        protocol_engine: InteractionProtocolEngine | None = None,
    ) -> None:
        self.serializer = serializer or JSONLDSerializer()
        self.parser = parser or MessageParser(self.serializer)
        self.mapper = mapper or PerformativeMapper()
        self.protocol_engine = protocol_engine or InteractionProtocolEngine()
        self.processed = 0
        self.rejected = 0

    # ------------------------------------------------------------------
    def inbound(self, data: str | Dict[str, Any] | ACLMessage) -> AdaptationResult:
        """Processa uma mensagem **recebida** (JSON-LD ou objeto)."""
        if isinstance(data, ACLMessage):
            result: ParseResult = self.parser.validate(data)
        else:
            result = self.parser.parse_jsonld(data)

        if not result.valid or result.message is None:
            self.rejected += 1
            return AdaptationResult(False, result.message, errors=result.errors)

        msg = result.message
        act = self.mapper.act_of(msg.performative)

        # Atualiza a máquina de estado do protocolo
        valid, state = self.protocol_engine.transition(
            msg.conversation_id, msg.performative, msg.protocol
        )
        if not valid:
            self.rejected += 1
            return AdaptationResult(
                False, msg, act, state,
                errors=[f"Transição inválida: {msg.performative.value} em {state.value}"],
            )

        self.processed += 1
        return AdaptationResult(True, msg, act, state)

    # ------------------------------------------------------------------
    def outbound(self, msg: ACLMessage) -> str:
        """Processa uma mensagem **enviada**, retornando JSON-LD."""
        # Registra a transição de saída (best-effort)
        if msg.conversation_id:
            self.protocol_engine.transition(
                msg.conversation_id, msg.performative, msg.protocol
            )
        return self.serializer.serialize(msg)

    # ------------------------------------------------------------------
    def validate_reply(
        self, original: Performative, reply: Performative
    ) -> bool:
        """Valida coerência de uma resposta em relação à mensagem original."""
        return self.mapper.is_valid_reply(original, reply)

    def summary(self) -> Dict[str, Any]:
        return {
            "processed": self.processed,
            "rejected": self.rejected,
            "parser": self.parser.summary(),
            "protocols": self.protocol_engine.summary(),
        }
