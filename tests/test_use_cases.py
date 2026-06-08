"""Testes dos casos de uso do estudo de caso (seção 3.3) do IIAE-BR.

Cobre os três casos de uso executados sobre as cinco camadas:

* **UC1** — Consultar Produto e Disponibilidade;
* **UC2** — Calcular Prazo e Frete (com tradução semântica
  Schema.org ↔ GoodRelations);
* **UC3** — Processar Pedido (ponta a ponta).

Valida ainda a coleta de métricas (latência e *overhead* por camada) e a
agregação Monte Carlo no formato consumido pela análise.
"""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.layer_1_application.logistics_agent import LogisticsAgent
from src.layer_1_application.sales_agent import SalesAgent
from src.layer_2_orchestration.load_balancer import LoadBalancer
from src.layer_2_orchestration.orchestrator import Orchestrator
from src.layer_3_interoperability.agent_registry import AgentRegistry
from src.layer_3_interoperability.semantic_mediator.mediator import (
    SemanticMediator,
)
from src.simulation.monte_carlo import MonteCarloSimulation
from src.simulation.scenarios import DEFAULT_SCENARIOS
from src.simulation.use_cases import LAYER_NAMES, UseCaseSimulator


def _build_simulator(seed: int = 0) -> UseCaseSimulator:
    """Monta um ``UseCaseSimulator`` sintético (sem dataset Olist)."""
    rng = random.Random(seed)
    sales = SalesAgent("sales_1", rng=rng)
    logistics = LogisticsAgent("log_1", rng=rng)
    registry = AgentRegistry()
    registry.register("sales_1", "sales", "schema.org")
    registry.register("log_1", "logistics", "goodrelations")
    orchestrator = Orchestrator(registry=registry, load_balancer=LoadBalancer())
    mediator = SemanticMediator()
    return UseCaseSimulator(sales, logistics, orchestrator, mediator, rng=rng)


# ---------------------------------------------------------------------------
# UC1 — Consultar Produto e Disponibilidade
# ---------------------------------------------------------------------------
def test_uc1_consultar_produto():
    sim = _build_simulator()
    res = sim.execute_uc1_consultar_produto(product_id="PROD-1")
    assert res.success is True
    assert res.use_case == "uc1"
    assert res.latency_ms > 0
    assert res.payload["product"]["@type"] == "Product"
    assert res.payload["offer"]["@type"] == "Offer"
    assert res.n_translations == 0  # fluxo intra-vocabulário
    # Mede overhead nas cinco camadas
    assert set(res.layer_overhead_ms.keys()) == set(LAYER_NAMES)


# ---------------------------------------------------------------------------
# UC2 — Calcular Prazo e Frete (tradução semântica bidirecional)
# ---------------------------------------------------------------------------
def test_uc2_calcular_entrega_traducao_semantica():
    sim = _build_simulator()
    res = sim.execute_uc2_calcular_entrega(
        seller_zip=1000, customer_zip=20000, peso_kg=2.0
    )
    assert res.success is True
    assert res.use_case == "uc2"
    assert res.payload["prazo_dias"] >= 1
    assert res.payload["valor_frete"] > 0
    # Duas traduções: Schema.org -> GoodRelations (req) e o inverso (resp)
    assert res.n_translations == 2
    # A resposta GoodRelations (Offering) é traduzida para Schema.org (Offer)
    assert res.payload["response_goodrelations"]["@type"] == "Offering"
    assert res.payload["response_schema_org"]["@type"] == "Offer"


def test_uc2_modalidade_express_mais_rapida():
    sim = _build_simulator()
    std = sim.execute_uc2_calcular_entrega(
        seller_zip=1000, customer_zip=90000, peso_kg=1.0, modalidade="standard"
    )
    exp = sim.execute_uc2_calcular_entrega(
        seller_zip=1000, customer_zip=90000, peso_kg=1.0, modalidade="express"
    )
    # Expresso: prazo menor ou igual e frete maior que o padrão
    assert exp.payload["prazo_dias"] <= std.payload["prazo_dias"]
    assert exp.payload["valor_frete"] > std.payload["valor_frete"]


# ---------------------------------------------------------------------------
# UC3 — Processar Pedido (ponta a ponta)
# ---------------------------------------------------------------------------
def test_uc3_processar_pedido_ponta_a_ponta():
    sim = _build_simulator()
    pedido = {
        "customer_id": "cliente-1",
        "items": [{"product_id": "PROD-1", "price": 100.0}],
        "seller_zip": 1000,
        "customer_zip": 20000,
        "total_weight_kg": 1.5,
    }
    # Força disponibilidade para um fluxo determinístico de sucesso
    sim.sales.stock_probability = 1.0
    res = sim.execute_uc3_processar_pedido(pedido_data=pedido)
    assert res.success is True
    assert res.use_case == "uc3"
    assert res.payload["status"] == "OrderConfirmed"
    assert res.payload["prazo_dias"] >= 1
    assert res.payload["valor_frete"] > 0
    assert res.n_translations == 2


# ---------------------------------------------------------------------------
# Cache semântico reduz o overhead de interoperabilidade
# ---------------------------------------------------------------------------
def test_cache_reduz_overhead_interoperabilidade():
    sim = _build_simulator()
    sim.configure_cache(0.0)
    soma0 = sum(
        sim.execute_uc2_calcular_entrega(seller_zip=1000, customer_zip=20000)
        .layer_overhead_ms["interoperabilidade"]
        for _ in range(400)
    )
    sim.configure_cache(0.95)
    soma95 = sum(
        sim.execute_uc2_calcular_entrega(seller_zip=1000, customer_zip=20000)
        .layer_overhead_ms["interoperabilidade"]
        for _ in range(400)
    )
    assert soma95 < soma0


# ---------------------------------------------------------------------------
# Agregação Monte Carlo no formato consumido pela análise
# ---------------------------------------------------------------------------
def test_monte_carlo_simulation_agrega_resultados():
    sim = _build_simulator()
    mc_sim = MonteCarloSimulation(
        sim, scenarios=DEFAULT_SCENARIOS[:2], cache_levels=[0.0, 0.8]
    )
    mc = mc_sim.run_simulation(
        num_iterations=100, scenario=DEFAULT_SCENARIOS[0],
        use_case="uc2", cache_level=0.0, progress=False,
    )
    assert mc.n_iterations == 100
    assert len(mc.mean_latencies) == 100
    assert len(mc.p95_latencies) == 1
    assert len(mc.throughputs) == 100
    assert all(name in mc.layer_overheads for name in LAYER_NAMES)
    assert len(mc.layer_overheads["interoperabilidade"]) == 100


def test_monte_carlo_experiment_combinacoes():
    sim = _build_simulator()
    mc_sim = MonteCarloSimulation(
        sim, scenarios=DEFAULT_SCENARIOS[:2], cache_levels=[0.0, 0.8]
    )
    resultados = mc_sim.run_experiment(
        num_iterations=50, use_case="uc1", progress=False
    )
    # 2 cenários × 2 níveis de cache = 4 combinações
    assert len(resultados) == 4
    nomes = {r.scenario_name for r in resultados}
    assert nomes == {"Normal", "Pico"}
