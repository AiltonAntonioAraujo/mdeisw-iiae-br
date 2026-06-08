"""Monte Carlo simulation runner for the IIAE-BR experiment.

Executes multiple independent simulation runs for each scenario ×
cache-level combination and aggregates results for statistical
analysis.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
from tqdm import tqdm

from src.simulation.engine import RunResult, run_simulation
from src.simulation.scenarios import DEFAULT_SCENARIOS, Scenario
from src.utils.data_loader import DatasetMetrics

logger = logging.getLogger(__name__)

# Níveis de cache padrão para a análise de sensibilidade (camada 3).
DEFAULT_CACHE_LEVELS: List[float] = [0.0, 0.50, 0.80, 0.95]


@dataclass
class MCResult:
    """Aggregated result for one (scenario, cache_level) combination."""

    scenario_name: str
    load_multiplier: float
    cache_level: float
    n_iterations: int

    # Arrays of per-iteration aggregates
    mean_latencies: List[float] = field(default_factory=list)
    p50_latencies: List[float] = field(default_factory=list)
    p95_latencies: List[float] = field(default_factory=list)
    p99_latencies: List[float] = field(default_factory=list)
    throughputs: List[float] = field(default_factory=list)
    rejection_rates: List[float] = field(default_factory=list)

    # Overhead por camada da arquitetura IIAE-BR (médias por iteração)
    total_overheads: List[float] = field(default_factory=list)
    layer_overheads: Dict[str, List[float]] = field(
        default_factory=lambda: {
            "aplicacao": [], "orquestracao": [], "interoperabilidade": [],
            "comunicacao": [], "infraestrutura": [],
        }
    )

    elapsed_s: float = 0.0


def run_monte_carlo(
    metrics: DatasetMetrics,
    scenarios: List[Scenario],
    cache_levels: List[float],
    n_iterations: int = 10_000,
    sim_duration_s: float = 10.0,
    warmup_s: float = 1.0,
    base_seed: int = 42,
    n_buyers: int = 50,
    n_sellers: int = 20,
    n_mediators: int = 3,
    n_logistics: int = 5,
    agent_kwargs: Optional[Dict[str, Any]] = None,
    progress: bool = True,
) -> List[MCResult]:
    """Run the full Monte Carlo experiment.

    Args:
        metrics: Dataset-derived metrics.
        scenarios: List of load scenarios.
        cache_levels: Cache hit-rate levels for sensitivity analysis.
        n_iterations: Number of Monte Carlo iterations per combination.
        sim_duration_s: Simulated time per run.
        warmup_s: Warm-up time per run.
        base_seed: Base random seed.
        n_buyers: Buyer agents per run.
        n_sellers: Seller agents per run.
        n_mediators: Mediator agents per run.
        n_logistics: Logistics agents per run.
        agent_kwargs: Extra kwargs for agents.
        progress: Show tqdm progress bar.

    Returns:
        List of :class:`MCResult` — one per (scenario, cache_level).
    """
    results: List[MCResult] = []
    total = len(scenarios) * len(cache_levels)
    combo_idx = 0

    for scenario in scenarios:
        for cache_level in cache_levels:
            combo_idx += 1
            label = f"[{combo_idx}/{total}] {scenario.name} cache={cache_level:.0%}"
            logger.info("Starting %s — %d iterations", label, n_iterations)
            t0 = time.time()

            mc = MCResult(
                scenario_name=scenario.name,
                load_multiplier=scenario.load_multiplier,
                cache_level=cache_level,
                n_iterations=n_iterations,
            )

            iterator = range(n_iterations)
            if progress:
                iterator = tqdm(iterator, desc=label, leave=False)

            for i in iterator:
                seed_i = base_seed + combo_idx * 100_000 + i
                rr: RunResult = run_simulation(
                    metrics=metrics,
                    load_multiplier=scenario.load_multiplier,
                    cache_hit_rate=cache_level,
                    duration_s=sim_duration_s,
                    warmup_s=warmup_s,
                    n_buyers=n_buyers,
                    n_sellers=n_sellers,
                    n_mediators=n_mediators,
                    n_logistics=n_logistics,
                    seed=seed_i,
                    agent_kwargs=agent_kwargs,
                )

                lats = rr.latencies_ms
                if lats:
                    mc.mean_latencies.append(float(np.mean(lats)))
                    mc.p50_latencies.append(float(np.percentile(lats, 50)))
                    mc.p95_latencies.append(float(np.percentile(lats, 95)))
                    mc.p99_latencies.append(float(np.percentile(lats, 99)))
                else:
                    mc.mean_latencies.append(0.0)
                    mc.p50_latencies.append(0.0)
                    mc.p95_latencies.append(0.0)
                    mc.p99_latencies.append(0.0)

                mc.throughputs.append(rr.throughput)
                mc.rejection_rates.append(rr.rejection_rate)

                # Overhead por camada (TASK 8)
                lo = rr.layer_overhead
                if lo:
                    mc.total_overheads.append(lo.get("avg_total_overhead_ms", 0.0))
                    for name, vals in mc.layer_overheads.items():
                        vals.append(lo["avg_per_layer_ms"].get(name, 0.0))

            mc.elapsed_s = time.time() - t0
            logger.info("%s completed in %.1fs", label, mc.elapsed_s)
            results.append(mc)

    return results



# ======================================================================
# Simulação Monte Carlo orientada a CASOS DE USO (estudo de caso 3.3)
# ======================================================================
class MonteCarloSimulation:
    """Simulação Monte Carlo sobre os casos de uso do estudo de caso.

    Diferentemente de :func:`run_monte_carlo` (motor estatístico de
    calibração), esta classe executa, a cada iteração, um **caso de uso
    real** (UC1/UC2/UC3) através das cinco camadas da arquitetura
    IIAE-BR, usando os agentes, o orquestrador e o mediador semântico.
    Agrega as latências e o *overhead* por camada no formato
    :class:`MCResult`, preservando o contrato consumido pelos módulos de
    análise (``metrics``/``report``/``charts``/``statistics``).

    Parameters:
        simulator: Instância de ``UseCaseSimulator`` (5 camadas montadas).
        scenarios: Cenários de carga. Padrão: os quatro do experimento.
        cache_levels: Níveis de acerto de cache para a análise de
            sensibilidade. Padrão: ``[0.0, 0.50, 0.60, 0.80, 0.95]``.
        base_seed: Semente-base para reprodutibilidade.
    """

    def __init__(
        self,
        simulator: Any,
        scenarios: Optional[List[Scenario]] = None,
        cache_levels: Optional[List[float]] = None,
        base_seed: int = 42,
    ) -> None:
        self.simulator = simulator
        self.scenarios = scenarios or list(DEFAULT_SCENARIOS)
        self.cache_levels = cache_levels or list(DEFAULT_CACHE_LEVELS)
        self.base_seed = base_seed

    # ------------------------------------------------------------------
    def run_simulation(
        self,
        num_iterations: int = 10_000,
        scenario: Optional[Scenario] = None,
        use_case: str = "uc3",
        cache_level: float = 0.0,
        progress: bool = True,
    ) -> MCResult:
        """Executa a simulação Monte Carlo de um caso de uso.

        Cada iteração corresponde a **uma transação** do caso de uso
        ``use_case`` sob o cenário de carga ``scenario`` e o nível de
        cache ``cache_level``. As latências individuais são agregadas em
        um :class:`MCResult`.

        Args:
            num_iterations: Número de iterações Monte Carlo.
            scenario: Cenário de carga. Se ``None``, usa o primeiro cenário.
            use_case: Caso de uso (``uc1``/``uc2``/``uc3``).
            cache_level: Taxa de acerto do cache semântico (camada 3).
            progress: Exibe barra de progresso.

        Returns:
            :class:`MCResult` agregado da combinação executada.
        """
        scenario = scenario or self.scenarios[0]
        self.simulator.configure_cache(cache_level)

        mc = MCResult(
            scenario_name=scenario.name,
            load_multiplier=scenario.load_multiplier,
            cache_level=cache_level,
            n_iterations=num_iterations,
        )

        t0 = time.time()
        latencies: List[float] = []
        overhead_acc = {name: [] for name in mc.layer_overheads}
        total_over: List[float] = []
        rejections = 0

        label = f"{scenario.name} {use_case} cache={cache_level:.0%}"
        iterator = range(num_iterations)
        if progress:
            iterator = tqdm(iterator, desc=label, leave=False)

        for _ in iterator:
            res = self.simulator.execute(
                use_case, load_multiplier=scenario.load_multiplier
            )
            latencies.append(res.latency_ms)
            total_over.append(res.total_overhead_ms)
            for name in overhead_acc:
                overhead_acc[name].append(res.layer_overhead_ms.get(name, 0.0))
            if not res.success:
                rejections += 1
            # Throughput instantâneo (transações/s) a partir da latência
            mc.throughputs.append(1000.0 / res.latency_ms if res.latency_ms else 0.0)
            mc.rejection_rates.append(0.0 if res.success else 1.0)

        # Agregados de latência: a média recebe TODAS as latências (np.mean
        # devolve a média global); os percentis são pré-computados sobre a
        # amostra completa e armazenados como elemento único (np.mean = valor).
        if latencies:
            mc.mean_latencies = list(latencies)
            mc.p50_latencies = [float(np.percentile(latencies, 50))]
            mc.p95_latencies = [float(np.percentile(latencies, 95))]
            mc.p99_latencies = [float(np.percentile(latencies, 99))]
        else:
            mc.mean_latencies = [0.0]
            mc.p50_latencies = [0.0]
            mc.p95_latencies = [0.0]
            mc.p99_latencies = [0.0]

        mc.total_overheads = total_over
        for name in mc.layer_overheads:
            mc.layer_overheads[name] = overhead_acc[name]

        mc.elapsed_s = time.time() - t0
        logger.info(
            "%s — %d iterações em %.1fs (rejeições=%d)",
            label, num_iterations, mc.elapsed_s, rejections,
        )
        return mc

    # ------------------------------------------------------------------
    def run_experiment(
        self,
        num_iterations: int = 10_000,
        scenarios: Optional[List[Scenario]] = None,
        cache_levels: Optional[List[float]] = None,
        use_case: str = "uc3",
        progress: bool = True,
    ) -> List[MCResult]:
        """Executa o experimento completo (cenários × níveis de cache).

        Args:
            num_iterations: Iterações Monte Carlo por combinação.
            scenarios: Cenários de carga. Se ``None``, usa os da instância.
            cache_levels: Níveis de cache. Se ``None``, usa os da instância.
            use_case: Caso de uso a executar.
            progress: Exibe barra de progresso.

        Returns:
            Lista de :class:`MCResult` — uma por (cenário, nível de cache).
        """
        scenarios = scenarios or self.scenarios
        cache_levels = cache_levels or self.cache_levels
        results: List[MCResult] = []
        total = len(scenarios) * len(cache_levels)
        idx = 0
        for scenario in scenarios:
            for cache_level in cache_levels:
                idx += 1
                logger.info(
                    "[%d/%d] %s cache=%.0f%% — %d iterações",
                    idx, total, scenario.name, cache_level * 100, num_iterations,
                )
                results.append(
                    self.run_simulation(
                        num_iterations=num_iterations,
                        scenario=scenario,
                        use_case=use_case,
                        cache_level=cache_level,
                        progress=progress,
                    )
                )
        return results
