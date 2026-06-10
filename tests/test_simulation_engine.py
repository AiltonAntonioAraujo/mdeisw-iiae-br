"""Testes do motor de simulação principal (:class:`SimulationEngine`).

Cobre:

* Carregamento da configuração e dos parâmetros (cenários, SLAs, cache);
* Execução de um cenário e a presença de todas as métricas especificadas
  (latência fim-a-fim, tradução, throughput, confiabilidade);
* Execução de todos os cenários;
* Análise de sensibilidade do cache (0 %, 50 %, 80 %, 95 %);
* O :class:`SemanticMediator` (``set_cache_hit_rate`` e
  ``translate_with_timing``).
"""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = str(PROJECT_ROOT / "configs" / "iiae_br_config.yaml")

import pytest

from src.layer_1_application.logistics_agent import LogisticsAgent
from src.layer_1_application.sales_agent import SalesAgent
from src.layer_2_orchestration.load_balancer import LoadBalancer
from src.layer_2_orchestration.orchestrator import Orchestrator
from src.layer_3_interoperability.agent_registry import AgentRegistry
from src.layer_3_interoperability.semantic_mediator.mediator import SemanticMediator
from src.simulation.engine import SimulationEngine
from src.utils.data_loader import OlistDataset


def _build_engine(
    iterations: int = 300, dataset: object = None
) -> SimulationEngine:
    """Monta um ``SimulationEngine`` com os componentes das cinco camadas.

    Args:
        iterations: Número de iterações Monte Carlo por cenário.
        dataset: ``OlistDataset`` real opcional. Quando ``None``, o motor
            usa a carga sintética equivalente.
    """
    rng = random.Random(0)
    sales = SalesAgent("sales-001", dataset_olist=dataset, rng=rng)
    logistics = LogisticsAgent("logistics-001", dataset_olist=dataset, rng=rng)
    registry = AgentRegistry()
    registry.register("sales-001", "sales", "schema.org")
    registry.register("logistics-001", "logistics", "goodrelations")
    orchestrator = Orchestrator(registry=registry, load_balancer=LoadBalancer())
    mediator = SemanticMediator()

    engine = SimulationEngine(CONFIG_PATH)
    engine.set_components(sales, logistics, orchestrator, mediator, dataset=dataset)
    engine.sim_config["iterations"] = iterations
    return engine


def _load_dataset_or_skip() -> OlistDataset:
    """Carrega o dataset Olist real; pula o teste se indisponível."""
    ds = OlistDataset.load(PROJECT_ROOT / "data")
    resumo = ds.summary()
    if resumo.get("orders", 0) == 0 or resumo.get("products", 0) == 0:
        pytest.skip("Dataset Olist indisponível em data/")
    return ds


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
def test_config_loaded():
    engine = _build_engine()
    assert engine.scenarios["pico"]["load_multiplier"] == 3.0
    assert engine.scenarios["normal"]["load_multiplier"] == 1.0
    assert engine.scenarios["blackfriday"]["load_multiplier"] == 10.0
    assert engine.scenarios["estresse"]["load_multiplier"] == 20.0


def test_cache_rates_config():
    engine = _build_engine()
    assert engine.interop["cache_hit_rates"] == [0.0, 0.5, 0.8, 0.95]


def test_slas_config():
    engine = _build_engine()
    assert engine.slas["latency_end_to_end"] == 150.0
    assert engine.slas["throughput_min"] == 1000.0
    assert engine.slas["rejection_rate"] == 0.01
    assert engine.slas["success_rate"] == 0.999


# ---------------------------------------------------------------------------
# Execução de cenário
# ---------------------------------------------------------------------------
def test_run_scenario_metrics():
    engine = _build_engine(iterations=300)
    res = engine.run_scenario("normal")

    # A) Latência fim-a-fim
    for key in ("latency_e2e_mean", "latency_e2e_median", "latency_e2e_std",
                "latency_e2e_p50", "latency_e2e_p95", "latency_e2e_p99"):
        assert key in res
        assert res[key] >= 0

    # B) Tradução
    assert 0.0 <= res["translation_rate"] <= 1.0
    assert res["translation_time_mean"] >= 0

    # C) Throughput
    assert res["throughput_mean"] >= 0
    assert res["throughput_max"] >= 0
    assert 0.0 <= res["rejection_rate"] <= 1.0

    # D) Confiabilidade
    assert 0.0 <= res["success_rate"] <= 1.0
    assert 0.0 <= res["timeout_rate"] <= 1.0
    assert 0.0 <= res["translation_error_rate"] <= 1.0

    assert res["scenario"] == "Normal"
    assert len(res["latencies_raw"]) == 300


def test_translation_rate_matches_use_case_mix():
    engine = _build_engine(iterations=2000)
    res = engine.run_scenario("normal")
    # UC2 (30 %) e UC3 (50 %) envolvem tradução semântica; UC1 (20 %) não.
    # Logo, ~80 % das transações requerem tradução.
    assert 0.7 <= res["translation_rate"] <= 0.9


def test_run_all_scenarios():
    engine = _build_engine(iterations=200)
    results = engine.run_all_scenarios()
    assert set(results.keys()) == {"normal", "pico", "blackfriday", "estresse"}
    # Maior carga -> maior taxa de rejeição
    assert results["estresse"]["rejection_rate"] >= results["normal"]["rejection_rate"]


# ---------------------------------------------------------------------------
# Análise de sensibilidade do cache
# ---------------------------------------------------------------------------
def test_cache_sensitivity_analysis():
    engine = _build_engine(iterations=500)
    results = engine.run_cache_sensitivity_analysis("normal")
    assert set(results.keys()) == {"0%", "50%", "80%", "95%"}
    assert results["0%"]["reduction_percent"] == 0.0
    # Cache mais alto reduz a latência de tradução em relação ao cache frio
    assert results["95%"]["translation_time_mean"] <= results["0%"]["translation_time_mean"]


# ---------------------------------------------------------------------------
# Distribuição de casos de uso e integração com o dataset Olist real
# ---------------------------------------------------------------------------
def test_use_case_distribution_present():
    engine = _build_engine(iterations=400)
    res = engine.run_scenario("normal")
    dist = res["use_case_distribution"]
    assert set(dist.keys()) == {"uc1", "uc2", "uc3"}
    assert sum(dist.values()) == 400
    # UC3 é o caso mais frequente (50 % do mix configurado).
    assert dist["uc3"] >= dist["uc1"]


def test_engine_runs_with_real_olist_dataset():
    """O motor executa os casos de uso reais sobre o dataset Olist."""
    dataset = _load_dataset_or_skip()
    engine = _build_engine(iterations=300, dataset=dataset)
    assert engine.dataset is dataset
    assert engine.use_case_sim is not None
    assert engine.use_case_sim.dataset is dataset

    res = engine.run_scenario("normal")
    assert len(res["latencies_raw"]) == 300
    assert res["latency_e2e_mean"] > 0
    # Latência fim-a-fim dentro de uma faixa plausível (SLA < 150 ms no
    # cenário normal).
    assert res["latency_e2e_mean"] < engine.slas["latency_end_to_end"]
    assert 0.7 <= res["translation_rate"] <= 0.9


# ---------------------------------------------------------------------------
# SemanticMediator
# ---------------------------------------------------------------------------
def test_mediator_set_cache_hit_rate():
    mediator = SemanticMediator()
    mediator.set_cache_hit_rate(0.95)
    assert mediator.cache_hit_rate == 0.95
    mediator.set_cache_hit_rate(1.5)  # clamp
    assert mediator.cache_hit_rate == 1.0
