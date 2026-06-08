"""Message Parser — Camada 3 (Interoperabilidade) / Protocol Adapter.

Responsável por **analisar (parse)** e **validar** mensagens FIPA-ACL,
tanto na forma de objeto :class:`ACLMessage` quanto na forma serializada
em JSON-LD. Garante que toda mensagem que entra na camada de
interoperabilidade respeita a estrutura mínima exigida pelo padrão
FIPA-ACL antes de ser encaminhada às demais etapas (mapeamento de
performativas, máquinas de estado de protocolo e mediação semântica).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from src.layer_4_communication.serialization import JSONLDSerializer
from src.layer_5_infrastructure.logging_service import get_logger
from src.utils.fipa_acl import ACLMessage, Performative

logger = get_logger(__name__)

# Campos obrigatórios de uma mensagem FIPA-ACL válida na IIAE-BR
REQUIRED_FIELDS = ("performative", "sender", "receiver")


@dataclass
class ParseResult:
    """Resultado da análise/validação de uma mensagem."""

    valid: bool
    message: ACLMessage | None = None
    errors: List[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


class MessageParser:
    """Analisa e valida mensagens FIPA-ACL (objeto ou JSON-LD)."""

    def __init__(self, serializer: JSONLDSerializer | None = None) -> None:
        self.serializer = serializer or JSONLDSerializer()
        self.parsed_count = 0
        self.error_count = 0

    # ------------------------------------------------------------------
    def parse_jsonld(self, data: str | Dict[str, Any]) -> ParseResult:
        """Analisa uma mensagem em JSON-LD (string ou dict)."""
        try:
            if isinstance(data, str):
                msg = self.serializer.deserialize(data)
            else:
                if not self.serializer.validate_schema(data):
                    self.error_count += 1
                    return ParseResult(False, None, ["JSON-LD inválido: campos ausentes"])
                msg = self.serializer.from_jsonld(data)
        except (KeyError, ValueError) as exc:  # pragma: no cover - defensivo
            self.error_count += 1
            return ParseResult(False, None, [f"Erro de parsing: {exc}"])
        return self.validate(msg)

    # ------------------------------------------------------------------
    def validate(self, msg: ACLMessage) -> ParseResult:
        """Valida a estrutura semântica de uma :class:`ACLMessage`."""
        errors: List[str] = []

        if not isinstance(msg.performative, Performative):
            errors.append("Performativa inválida ou ausente")
        if not msg.sender:
            errors.append("Campo 'sender' obrigatório")
        if not msg.receiver:
            errors.append("Campo 'receiver' obrigatório")

        # Mensagens que iniciam protocolo devem ter conversation_id
        if msg.performative in (
            Performative.REQUEST,
            Performative.CFP,
            Performative.QUERY_IF,
            Performative.QUERY_REF,
            Performative.SUBSCRIBE,
        ) and not msg.conversation_id:
            errors.append("conversation_id obrigatório para início de protocolo")

        if errors:
            self.error_count += 1
            logger.debug("Mensagem inválida: %s", errors)
            return ParseResult(False, msg, errors)

        self.parsed_count += 1
        return ParseResult(True, msg, [])

    # ------------------------------------------------------------------
    def summary(self) -> Dict[str, int]:
        return {"parsed": self.parsed_count, "errors": self.error_count}
