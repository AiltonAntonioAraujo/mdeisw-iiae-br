"""Tests for the FIPA-ACL message layer."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.fipa_acl import ACLMessage, MessageBus, Performative


def test_message_creation():
    msg = ACLMessage(
        performative=Performative.CFP,
        sender="buyer_01",
        receiver="mediator_00",
        content={"action": "purchase"},
        conversation_id="conv123",
    )
    assert msg.performative == Performative.CFP
    assert msg.sender == "buyer_01"
    assert msg.receiver == "mediator_00"


def test_message_reply():
    msg = ACLMessage(
        performative=Performative.CFP,
        sender="buyer_01",
        receiver="mediator_00",
        conversation_id="conv123",
    )
    reply = msg.create_reply(Performative.PROPOSE, content={"price": 99.0})
    assert reply.sender == "mediator_00"
    assert reply.receiver == "buyer_01"
    assert reply.performative == Performative.PROPOSE
    assert reply.conversation_id == "conv123"


def test_message_serialization():
    msg = ACLMessage(
        performative=Performative.INFORM,
        sender="a", receiver="b",
        content="hello",
    )
    d = msg.to_dict()
    msg2 = ACLMessage.from_dict(d)
    assert msg2.performative == msg.performative
    assert msg2.content == msg.content


def test_message_bus():
    bus = MessageBus()
    bus.register("agent_a")
    bus.register("agent_b")

    msg = ACLMessage(
        performative=Performative.REQUEST,
        sender="agent_a", receiver="agent_b",
        content="do_something",
    )
    bus.send(msg)

    assert bus.pending("agent_b") == 1
    assert bus.pending("agent_a") == 0

    received = bus.receive("agent_b")
    assert received is not None
    assert received.content == "do_something"
    assert bus.pending("agent_b") == 0
    assert bus.total_messages == 1


def test_message_bus_receive_all():
    bus = MessageBus()
    bus.register("x")
    for i in range(5):
        bus.send(ACLMessage(
            performative=Performative.INFORM,
            sender="y", receiver="x", content=i,
        ))
    msgs = bus.receive_all("x")
    assert len(msgs) == 5
    assert bus.pending("x") == 0
