"""Serialization — Camada 4 (Comunicação) do IIAE-BR.

Serialização e deserialização de mensagens FIPA-ACL no formato
**JSON-LD** (JSON for Linked Data), o formato principal de troca de
dados semânticos da arquitetura IIAE-BR.

JSON-LD permite anexar contexto semântico (``@context``) às mensagens,
viabilizando a interoperabilidade entre vocabulários Schema.org e
GoodRelations.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from src.utils.fipa_acl import ACLMessage, Performative

# Contexto JSON-LD padrão da arquitetura
DEFAULT_CONTEXT: Dict[str, Any] = {
    "@vocab": "http://iiae-br.org/ontology#",
    "schema": "http://schema.org/",
    "gr": "http://purl.org/goodrelations/v1#",
    "fipa": "http://www.fipa.org/schemas#",
    "performative": "fipa:performative",
    "sender": "fipa:sender",
    "receiver": "fipa:receiver",
    "content": "fipa:content",
    "conversationId": "fipa:conversation-id",
    "protocol": "fipa:protocol",
    "ontology": "fipa:ontology",
}


class JSONLDSerializer:
    """Serializador JSON-LD para mensagens FIPA-ACL."""

    def __init__(self, context: Dict[str, Any] | None = None) -> None:
        self.context = context or DEFAULT_CONTEXT
        self.serialized_count = 0
        self.deserialized_count = 0

    # ------------------------------------------------------------------

    def serialize(self, msg: ACLMessage) -> str:
        """Serializa uma :class:`ACLMessage` para string JSON-LD."""
        doc = self.to_jsonld(msg)
        self.serialized_count += 1
        return json.dumps(doc, ensure_ascii=False)

    def to_jsonld(self, msg: ACLMessage) -> Dict[str, Any]:
        """Converte uma :class:`ACLMessage` em documento JSON-LD."""
        return {
            "@context": self.context,
            "@type": "fipa:ACLMessage",
            "@id": f"urn:msg:{msg.message_id}",
            "performative": msg.performative.value,
            "sender": msg.sender,
            "receiver": msg.receiver,
            "content": msg.content,
            "conversationId": msg.conversation_id,
            "replyWith": msg.reply_with,
            "inReplyTo": msg.in_reply_to,
            "language": msg.language,
            "ontology": msg.ontology,
            "protocol": msg.protocol,
            "timestamp": msg.timestamp,
            "messageId": msg.message_id,
        }

    # ------------------------------------------------------------------

    def deserialize(self, data: str) -> ACLMessage:
        """Deserializa uma string JSON-LD em :class:`ACLMessage`."""
        doc = json.loads(data)
        return self.from_jsonld(doc)

    def from_jsonld(self, doc: Dict[str, Any]) -> ACLMessage:
        """Converte um documento JSON-LD em :class:`ACLMessage`."""
        self.deserialized_count += 1
        return ACLMessage(
            performative=Performative(doc["performative"]),
            sender=doc["sender"],
            receiver=doc["receiver"],
            content=doc.get("content"),
            conversation_id=doc.get("conversationId", ""),
            reply_with=doc.get("replyWith", ""),
            in_reply_to=doc.get("inReplyTo", ""),
            language=doc.get("language", "fipa-sl"),
            ontology=doc.get("ontology", "iiae-br-ontology"),
            protocol=doc.get("protocol", ""),
            timestamp=doc.get("timestamp", 0.0),
            message_id=doc.get("messageId", ""),
        )

    # ------------------------------------------------------------------

    def validate_schema(self, doc: Dict[str, Any]) -> bool:
        """Valida a estrutura mínima de um documento JSON-LD FIPA-ACL."""
        required = ("@context", "@type", "performative", "sender", "receiver")
        return all(key in doc for key in required)

    def summary(self) -> Dict[str, int]:
        return {
            "serialized": self.serialized_count,
            "deserialized": self.deserialized_count,
        }
