"""FIPA-ACL message layer for the IIAE-BR experiment.

Implements the FIPA Agent Communication Language (FIPA-ACL) message
structure following the FIPA specification (SC00061G).  This module
provides a lightweight, pure-Python implementation that does **not**
require an XMPP server, making it suitable for discrete-event
simulation with SimPy.

Performatives follow FIPA Communicative Act Library (SC00037J):
    INFORM, REQUEST, AGREE, REFUSE, PROPOSE, ACCEPT_PROPOSAL,
    REJECT_PROPOSAL, CFP (Call for Proposal), QUERY_IF, NOT_UNDERSTOOD,
    FAILURE, CANCEL.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class Performative(str, Enum):
    """FIPA-ACL communicative acts."""

    INFORM = "inform"
    REQUEST = "request"
    AGREE = "agree"
    REFUSE = "refuse"
    PROPOSE = "propose"
    ACCEPT_PROPOSAL = "accept-proposal"
    REJECT_PROPOSAL = "reject-proposal"
    CFP = "cfp"
    QUERY_IF = "query-if"
    QUERY_REF = "query-ref"
    SUBSCRIBE = "subscribe"
    CONFIRM = "confirm"
    NOT_UNDERSTOOD = "not-understood"
    FAILURE = "failure"
    CANCEL = "cancel"


@dataclass
class ACLMessage:
    """A FIPA-ACL message.

    Attributes:
        performative: Communicative act type.
        sender: Agent identifier of the sender.
        receiver: Agent identifier of the receiver.
        content: Message payload (serialisable dict or string).
        conversation_id: Groups messages in a conversation.
        reply_with: Identifier for expected reply.
        in_reply_to: References previous ``reply_with``.
        language: Content language (default ``fipa-sl``).
        ontology: Ontology used for content interpretation.
        protocol: Interaction protocol (e.g., ``fipa-contract-net``).
        timestamp: Unix epoch when message was created.
        message_id: Unique identifier for this message.
    """

    performative: Performative
    sender: str
    receiver: str
    content: Any = None
    conversation_id: str = ""
    reply_with: str = ""
    in_reply_to: str = ""
    language: str = "fipa-sl"
    ontology: str = "iiae-br-ontology"
    protocol: str = ""
    timestamp: float = field(default_factory=time.time)
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    # ---- helpers ----

    def create_reply(
        self,
        performative: Performative,
        content: Any = None,
    ) -> "ACLMessage":
        """Create a reply to this message, swapping sender/receiver."""
        return ACLMessage(
            performative=performative,
            sender=self.receiver,
            receiver=self.sender,
            content=content,
            conversation_id=self.conversation_id,
            in_reply_to=self.reply_with or self.message_id,
            language=self.language,
            ontology=self.ontology,
            protocol=self.protocol,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dictionary."""
        return {
            "performative": self.performative.value,
            "sender": self.sender,
            "receiver": self.receiver,
            "content": self.content,
            "conversation_id": self.conversation_id,
            "reply_with": self.reply_with,
            "in_reply_to": self.in_reply_to,
            "language": self.language,
            "ontology": self.ontology,
            "protocol": self.protocol,
            "timestamp": self.timestamp,
            "message_id": self.message_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ACLMessage":
        """Deserialise from a plain dictionary."""
        data = dict(data)
        data["performative"] = Performative(data["performative"])
        return cls(**data)

    def __str__(self) -> str:
        return (
            f"ACLMessage({self.performative.value} "
            f"from={self.sender} to={self.receiver} "
            f"conv={self.conversation_id})"
        )


class MessageBus:
    """In-process message bus for agent communication.

    Agents register mailboxes identified by their ``agent_id``.
    Messages are enqueued into the receiver's mailbox synchronously.
    Thread-safe is **not** needed because SimPy is single-threaded.
    """

    def __init__(self) -> None:
        self._mailboxes: Dict[str, list[ACLMessage]] = {}
        self._message_log: list[ACLMessage] = []

    def register(self, agent_id: str) -> None:
        """Register an agent mailbox."""
        if agent_id not in self._mailboxes:
            self._mailboxes[agent_id] = []

    def send(self, msg: ACLMessage) -> None:
        """Deliver *msg* to the receiver's mailbox."""
        self._message_log.append(msg)
        target = msg.receiver
        if target not in self._mailboxes:
            self._mailboxes[target] = []
        self._mailboxes[target].append(msg)

    def receive(self, agent_id: str) -> Optional[ACLMessage]:
        """Pop the oldest message from *agent_id*'s mailbox, or None."""
        mbox = self._mailboxes.get(agent_id, [])
        return mbox.pop(0) if mbox else None

    def receive_all(self, agent_id: str) -> list[ACLMessage]:
        """Drain all messages from *agent_id*'s mailbox."""
        mbox = self._mailboxes.get(agent_id, [])
        msgs = list(mbox)
        mbox.clear()
        return msgs

    def pending(self, agent_id: str) -> int:
        """Number of unread messages for *agent_id*."""
        return len(self._mailboxes.get(agent_id, []))

    @property
    def total_messages(self) -> int:
        """Total messages sent through the bus."""
        return len(self._message_log)

    @property
    def log(self) -> list[ACLMessage]:
        return list(self._message_log)
