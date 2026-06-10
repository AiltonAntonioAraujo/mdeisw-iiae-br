"""Testes da arquitetura em 5 camadas do IIAE-BR.

Cobre:
* Camada 4 — serialização JSON-LD (round-trip);
* Camada 3 — adaptador FIPA-ACL (parsing, performativas, máquinas de
  estado dos protocolos) e mediação semântica bidirecional
  (Schema.org ↔ GoodRelations) com cache configurável;
* Camada 2 — orquestração (roteamento, prioridade, round-robin);
* Camada 1 — agentes de aplicação (Schema.org / GoodRelations);
* Camada 5 — serviços de infraestrutura (config, monitoramento);
* Integração — medição de overhead por camada na simulação.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.fipa_acl import ACLMessage, Performative


# ---------------------------------------------------------------------------
# Camada 4 — Comunicação (Serialização JSON-LD)
# ---------------------------------------------------------------------------
def test_jsonld_round_trip():
    from src.layer_4_communication.serialization import JSONLDSerializer

    ser = JSONLDSerializer()
    msg = ACLMessage(
        performative=Performative.REQUEST,
        sender="sales_1", receiver="log_1",
        conversation_id="c1", protocol="fipa-request",
        content={"weight_kg": 2.0},
    )
    data = ser.serialize(msg)
    assert isinstance(data, str)
    restored = ser.deserialize(data)
    assert restored.performative == Performative.REQUEST
    assert restored.sender == "sales_1"
    assert restored.content == {"weight_kg": 2.0}


def test_jsonld_has_context():
    from src.layer_4_communication.serialization import JSONLDSerializer

    ser = JSONLDSerializer()
    msg = ACLMessage(performative=Performative.INFORM, sender="a", receiver="b")
    doc = ser.to_jsonld(msg)
    assert "@context" in doc
    assert ser.validate_schema(doc)


# ---------------------------------------------------------------------------
# Camada 3 — Protocol Adapter (FIPA-ACL)
# ---------------------------------------------------------------------------
def test_request_protocol_state_machine():
    from src.layer_3_interoperability.protocol_adapter import (
        FIPAACLAdapter,
        ProtocolState,
    )

    ad = FIPAACLAdapter()
    req = ACLMessage(performative=Performative.REQUEST, sender="a", receiver="b",
                     conversation_id="c1", protocol="fipa-request")
    r1 = ad.inbound(req)
    assert r1.accepted and r1.protocol_state == ProtocolState.PENDING

    agree = ACLMessage(performative=Performative.AGREE, sender="b", receiver="a",
                       conversation_id="c1", protocol="fipa-request")
    r2 = ad.inbound(agree)
    assert r2.protocol_state == ProtocolState.ACTIVE

    inform = ACLMessage(performative=Performative.INFORM, sender="b", receiver="a",
                        conversation_id="c1", protocol="fipa-request")
    r3 = ad.inbound(inform)
    assert r3.protocol_state == ProtocolState.COMPLETED


def test_invalid_protocol_transition_rejected():
    from src.layer_3_interoperability.protocol_adapter import FIPAACLAdapter

    ad = FIPAACLAdapter()
    # PROPOSE não é válido como início de uma conversa fipa-request
    bad = ACLMessage(performative=Performative.PROPOSE, sender="a", receiver="b",
                     conversation_id="cx", protocol="fipa-request")
    r = ad.inbound(bad)
    assert not r.accepted


def test_contract_net_protocol():
    from src.layer_3_interoperability.protocol_adapter import (
        InteractionProtocolEngine,
        ProtocolState,
    )

    eng = InteractionProtocolEngine()
    eng.start("c1", "fipa-contract-net")
    assert eng.transition("c1", Performative.CFP)[1] == ProtocolState.NEGOTIATING
    assert eng.transition("c1", Performative.PROPOSE)[1] == ProtocolState.PENDING
    assert eng.transition("c1", Performative.ACCEPT_PROPOSAL)[1] == ProtocolState.ACTIVE
    assert eng.transition("c1", Performative.INFORM)[1] == ProtocolState.COMPLETED


def test_subscribe_protocol_cancel():
    from src.layer_3_interoperability.protocol_adapter import (
        InteractionProtocolEngine,
        ProtocolState,
    )

    eng = InteractionProtocolEngine()
    eng.start("s1", "fipa-subscribe")
    eng.transition("s1", Performative.SUBSCRIBE)
    eng.transition("s1", Performative.AGREE)
    assert eng.transition("s1", Performative.CANCEL)[1] == ProtocolState.CANCELLED


def test_performative_valid_replies():
    from src.layer_3_interoperability.protocol_adapter import PerformativeMapper

    mapper = PerformativeMapper()
    assert mapper.is_valid_reply(Performative.REQUEST, Performative.AGREE)
    assert mapper.is_valid_reply(Performative.CFP, Performative.PROPOSE)
    assert not mapper.is_valid_reply(Performative.REQUEST, Performative.PROPOSE)


# ---------------------------------------------------------------------------
# Camada 3 — Semantic Mediator (Schema.org <-> GoodRelations)
# ---------------------------------------------------------------------------
def test_bidirectional_translation():
    from src.layer_3_interoperability.semantic_mediator import SemanticMediator

    med = SemanticMediator()
    product = {"@type": "Product", "name": "Cadeira", "sku": "SKU1",
               "price": 100.0, "priceCurrency": "BRL", "category": "moveis"}
    gr = med.translate(product, "goodrelations")
    assert gr["@type"] == "ProductOrService"
    assert gr["hasStockKeepingUnit"] == "SKU1"
    assert gr["hasCurrencyValue"] == 100.0

    back = med.translate(gr, "schema.org")
    assert back["@type"] == "Product"
    assert back["sku"] == "SKU1"
    assert back["price"] == 100.0


def test_vocabulary_detection():
    from src.layer_3_interoperability.semantic_mediator import SemanticMediator

    med = SemanticMediator()
    assert med.detect_vocabulary({"@type": "Product"}) == "schema.org"
    assert med.detect_vocabulary({"@type": "ProductOrService"}) == "goodrelations"
    assert med.detect_vocabulary({"@type": "Offer", "hasCurrencyValue": 5}) == "goodrelations"


def test_configurable_cache_hit_rate():
    from src.layer_3_interoperability.semantic_mediator import OntologyMapper

    mapper = OntologyMapper(forced_hit_rate=0.8)
    entity = {"@type": "Product", "name": "X", "sku": "S1"}
    for _ in range(200):
        mapper.schema_to_goodrelations(entity)
    summary = mapper.summary()
    # Tolerância pela natureza determinística do modo experimento
    assert abs(summary["hit_rate"] - 0.8) < 0.05
    # Acertos de cache devem ter overhead médio menor que misses
    assert summary["avg_overhead_ms"] > 0


def test_translation_overhead_decreases_with_cache():
    from src.layer_3_interoperability.semantic_mediator import OntologyMapper

    entity = {"@type": "Product", "name": "X", "sku": "S1"}

    low = OntologyMapper(forced_hit_rate=0.0)
    high = OntologyMapper(forced_hit_rate=0.95)
    for _ in range(200):
        low.schema_to_goodrelations(entity)
        high.schema_to_goodrelations(entity)
    assert high.summary()["avg_overhead_ms"] < low.summary()["avg_overhead_ms"]


# ---------------------------------------------------------------------------
# Camada 2 — Orquestração
# ---------------------------------------------------------------------------
def test_orchestrator_round_robin_routing():
    from src.layer_2_orchestration import Orchestrator
    from src.layer_3_interoperability import AgentRegistry

    reg = AgentRegistry()
    reg.register("log_1", "logistics", "goodrelations", ["frete"])
    reg.register("log_2", "logistics", "goodrelations", ["frete"])
    orch = Orchestrator(registry=reg)

    targets = []
    for _ in range(4):
        m = ACLMessage(performative=Performative.REQUEST, sender="s",
                       receiver="role:logistics", conversation_id="c")
        targets.append(orch.route(m).target)
    assert targets == ["log_1", "log_2", "log_1", "log_2"]


def test_orchestrator_priority_queue():
    from src.layer_2_orchestration import Orchestrator

    orch = Orchestrator()
    low = ACLMessage(performative=Performative.QUERY_IF, sender="a", receiver="b")
    high = ACLMessage(performative=Performative.ACCEPT_PROPOSAL, sender="a", receiver="b")
    orch.enqueue(low)
    orch.enqueue(high)
    # A de maior prioridade (accept-proposal) deve sair primeiro
    assert orch.dequeue().performative == Performative.ACCEPT_PROPOSAL


def test_load_balancer_least_loaded():
    from src.layer_2_orchestration import LoadBalancer

    lb = LoadBalancer(strategy="least_loaded")
    lb.register_pool("sales", ["s1", "s2", "s3"])
    chosen = {lb.select("sales") for _ in range(3)}
    assert chosen == {"s1", "s2", "s3"}


# ---------------------------------------------------------------------------
# Camada 1 — Aplicação
# ---------------------------------------------------------------------------
def test_sales_agent_uses_schema_org():
    from src.layer_1_application import SalesAgent
    import random

    agent = SalesAgent("sales_1", rng=random.Random(0))
    q = ACLMessage(performative=Performative.QUERY_REF, sender="buyer",
                   receiver="sales_1", conversation_id="c1",
                   content={"product_id": "P1", "price": 50.0})
    resp = agent.handle(q)
    assert resp.performative == Performative.INFORM
    assert resp.content["product"]["@type"] == "Product"
    assert resp.content["offer"]["@type"] == "Offer"


def test_logistics_agent_uses_goodrelations():
    from src.layer_1_application import LogisticsAgent
    import random

    agent = LogisticsAgent("log_1", rng=random.Random(0))
    req = ACLMessage(performative=Performative.REQUEST, sender="sales_1",
                     receiver="log_1", conversation_id="c1",
                     content={"weight_kg": 3.0, "distance_km": 200})
    resp = agent.handle(req)
    assert resp.performative == Performative.INFORM
    assert resp.content["priceSpecification"]["@type"] == "UnitPriceSpecification"
    assert resp.content["estimatedDays"] >= 1


# ---------------------------------------------------------------------------
# Camada 5 — Infraestrutura
# ---------------------------------------------------------------------------
def test_config_service_loads_layers():
    from src.layer_5_infrastructure.config_service import ConfigService

    cs = ConfigService()
    assert cs.layers == [
        "application", "orchestration", "interoperability",
        "communication", "infrastructure",
    ]
    assert cs.get("orchestration", "load_balancing") == "round_robin"


def test_monitoring_records_layer_overhead():
    from src.layer_5_infrastructure.monitoring_service import MonitoringService

    mon = MonitoringService()
    mon.record_layer_overhead("interoperabilidade", 1.5)
    mon.record_layer_overhead("interoperabilidade", 2.5)
    overheads = mon.layer_overheads()
    assert "interoperabilidade" in overheads


