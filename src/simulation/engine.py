"""Motor de Simulação Monte Carlo para a Arquitetura IIAE-BR.

Avalia quantitativamente a interoperabilidade entre o **SalesAgent**
(Schema.org) e o **LogisticsAgent** (GoodRelations) através das cinco
camadas da arquitetura IIAE-BR, usando o **dataset Olist real** e os
**casos de uso concretos** (UC1, UC2, UC3).

Implementa dois modos de operação:

#. :class:`SimulationEngine` — motor principal, dirigido por
   configuração (``configs/iiae_br_config.yaml``). A cada iteração Monte
   Carlo executa um **caso de uso real** (UC1/UC2/UC3) por meio do
   :class:`~src.simulation.use_cases.UseCaseSimulator`, que percorre as
   cinco camadas chamando concretamente os agentes, o orquestrador e o
   mediador semântico sobre dados reais do Olist. As métricas (latência
   fim-a-fim, tempo de tradução, throughput, confiabilidade) são
   agregadas a partir dessas execuções reais.
#. :func:`run_simulation` — gerador estatístico legado (compatibilidade
   com os testes existentes) baseado em :class:`DatasetMetrics`.
"""

from __future__ import annotations

import logging
import random
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import yaml

from src.simulation.layer_overhead import (
    LayerOverheadAccumulator,
    LayerOverheadModel,
)
from src.simulation.use_cases import UseCaseSimulator
from src.utils.data_loader import DatasetMetrics

logger = logging.getLogger(__name__)


# ======================================================================
# Motor de Simulação principal (dirigido por configuração)
# ======================================================================

class SimulationEngine:
    """Motor de Simulação Monte Carlo para a IIAE-BR.

    Executa uma simulação realista usando os casos de uso implementados
    nos agentes **Sales** e **Logistics** através das cinco camadas da
    arquitetura. Os parâmetros são lidos de ``configs/iiae_br_config.yaml``.

    Cada iteração Monte Carlo representa uma transação ponta a ponta,
    executada como um **caso de uso real** (UC1/UC2/UC3) por meio do
    :class:`~src.simulation.use_cases.UseCaseSimulator`:

    #. **Aplicação** — comportamentos concretos dos agentes (Schema.org /
       GoodRelations) sobre dados reais do Olist;
    #. **Orquestração** — roteamento FIPA-ACL via ``Orchestrator``;
    #. **Interoperabilidade** — mediação semântica (Schema.org ↔
       GoodRelations) com cache configurável;
    #. **Comunicação** — barramento FIPA-ACL;
    #. **Infraestrutura** — monitoramento/segurança.

    A distribuição das transações entre os casos de uso segue o
    ``use_case_mix`` da configuração (UC1 20 %, UC2 30 %, UC3 50 % por
    padrão). UC2 e UC3 envolvem tradução semântica; UC1 é intra-vocabulário.

    Parameters:
        config_path: Caminho para o arquivo de configuração YAML.
    """

    def __init__(
        self, config_path: str = "configs/iiae_br_config.yaml"
    ) -> None:
        with open(config_path, "r", encoding="utf-8") as fh:
            self.config: Dict[str, Any] = yaml.safe_load(fh)

        self.sim_config: Dict[str, Any] = self.config["simulation"]
        self.scenarios: Dict[str, Any] = self.config["scenarios"]
        self.slas: Dict[str, Any] = self.config["slas"]
        self.interop: Dict[str, Any] = (
            self.config["interoperability"]["semantic_mediator"]
        )

        # Mix de casos de uso (deve somar 1.0). UC1 sem tradução; UC2/UC3
        # com tradução semântica bidirecional.
        mix = self.sim_config.get(
            "use_case_mix", {"uc1": 0.20, "uc2": 0.30, "uc3": 0.50}
        )
        self._uc_keys = ["uc1", "uc2", "uc3"]
        self._uc_probs = [float(mix.get(k, 0.0)) for k in self._uc_keys]
        total_p = sum(self._uc_probs) or 1.0
        self._uc_probs = [p / total_p for p in self._uc_probs]

        # Gerador aleatório reprodutível (semente do experimento).
        seed = int(self.config.get("experiment", {}).get("seed", 42))
        self.rng = random.Random(seed)
        np.random.seed(seed % (2**31))

        # Componentes da arquitetura (injetados via set_components)
        self.sales_agent: Any = None
        self.logistics_agent: Any = None
        self.orchestrator: Any = None
        self.semantic_mediator: Any = None
        self.dataset: Any = None
        # Executor dos casos de uso reais (montado em set_components)
        self.use_case_sim: Optional[UseCaseSimulator] = None

        self.metrics: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    def set_components(
        self,
        sales_agent: Any,
        logistics_agent: Any,
        orchestrator: Any,
        semantic_mediator: Any,
        dataset: Any = None,
    ) -> None:
        """Injeta os componentes reais da arquitetura IIAE-BR e o dataset.

        Constrói internamente um :class:`UseCaseSimulator` que executa os
        casos de uso concretos (UC1/UC2/UC3) através das cinco camadas,
        usando os dados reais do Olist quando ``dataset`` é fornecido.

        Args:
            sales_agent: Agente de vendas (camada 1, Schema.org).
            logistics_agent: Agente de logística (camada 1, GoodRelations).
            orchestrator: Orquestrador de mensagens (camada 2).
            semantic_mediator: Mediador semântico (camada 3).
            dataset: Instância de ``OlistDataset`` (dados reais). Opcional.
        """
        self.sales_agent = sales_agent
        self.logistics_agent = logistics_agent
        self.orchestrator = orchestrator
        self.semantic_mediator = semantic_mediator
        self.dataset = dataset

        self.use_case_sim = UseCaseSimulator(
            sales_agent=sales_agent,
            logistics_agent=logistics_agent,
            orchestrator=orchestrator,
            semantic_mediator=semantic_mediator,
            dataset=dataset,
            rng=self.rng,
        )

    # ------------------------------------------------------------------
    def run_all_scenarios(self) -> Dict[str, Dict[str, Any]]:
        """Executa a simulação em todos os cenários configurados.

        Returns:
            Dicionário ``{chave_cenario: métricas}``.
        """
        results: Dict[str, Dict[str, Any]] = {}
        for scenario_key, scenario_config in self.scenarios.items():
            print(f"\n{'=' * 70}")
            print(f"Cenário: {scenario_config['name']}")
            print(f"Multiplicador: {scenario_config['load_multiplier']}x")
            print(f"{'=' * 70}")
            results[scenario_key] = self.run_scenario(scenario_key)
        return results

    # ------------------------------------------------------------------
    def run_scenario(self, scenario_key: str) -> Dict[str, Any]:
        """Executa a simulação Monte Carlo para um cenário.

        Args:
            scenario_key: ``normal`` | ``pico`` | ``blackfriday`` |
                ``estresse``.

        Returns:
            Dicionário com todas as métricas especificadas (A–D).
        """
        scenario = self.scenarios[scenario_key]
        n_iterations = int(self.sim_config["iterations"]* float(
            scenario["load_multiplier"]
        ))

        arrival_rate_per_hour = float(self.sim_config["arrival_rate_base"]) * float(
            scenario["load_multiplier"]
        )
        if arrival_rate_per_hour <= 0.0:
            raise ValueError("arrival_rate_base and load_multiplier must be positive")
        interarrival_ms = 3600000.0 / arrival_rate_per_hour
        interarrival_s = interarrival_ms / 1000.0

        latencies_end_to_end: List[float] = []
        latencies_translation: List[float] = []
        translation_counts = 0
        cache_hits = 0
        use_case_counts: Dict[str, int] = {"uc1": 0, "uc2": 0, "uc3": 0}
        message_counts: Dict[str, int] = {
            "success": 0,
            "timeout": 0,
            "rejection": 0,
            "translation_error": 0,
            "total": 0,
        }
        timestamps: List[float] = []

        current_time_s = time.perf_counter()

        for i in range(n_iterations):
            if (i + 1) % 2000 == 0:
                print(f"  Iterações: {i + 1}/{n_iterations}")

            while time.perf_counter() < current_time_s:
                pass  # Fica em loop rápido checando o tempo

            timestamps.append(current_time_s)
            tx = self._run_one_transaction(scenario)

            latencies_end_to_end.append(tx["latency_end_to_end"])
            use_case_counts[tx["use_case"]] = (
                use_case_counts.get(tx["use_case"], 0) + 1
            )

            if tx["translation_occurred"]:
                latencies_translation.append(tx["latency_translation"])
                translation_counts += 1
                if tx["cache_hit"]:
                    cache_hits += 1

            if tx["translation_error"]:
                message_counts["translation_error"] += 1

            if tx["timeout"]:
                message_counts["timeout"] += 1
            elif tx["rejected"]:
                message_counts["rejection"] += 1
            elif tx["success"]:
                message_counts["success"] += 1

            message_counts["total"] += 1

            current_time_s += interarrival_s

        if len(timestamps) > 1:
            sim_duration = timestamps[-1] - timestamps[0]
        elif len(timestamps) == 1:
            sim_duration = 0.0
        else:
            sim_duration = 0.0

        return self._calculate_metrics(
            latencies_end_to_end,
            latencies_translation,
            translation_counts,
            cache_hits,
            use_case_counts,
            message_counts,
            timestamps,
            sim_duration,
            scenario,
        )

    # ------------------------------------------------------------------
    def _run_one_transaction(
        self, scenario: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Executa **uma transação real** (UC1/UC2/UC3) da simulação.

        Sorteia o caso de uso conforme o ``use_case_mix`` da configuração
        e delega a execução ao :class:`UseCaseSimulator`, que percorre as
        cinco camadas chamando concretamente os agentes, o orquestrador e o
        mediador semântico sobre os **dados reais do Olist** (quando o
        dataset está disponível). As métricas (latência fim-a-fim, tempo de
        tradução, *cache hit*, sucesso) são derivadas do
        :class:`~src.simulation.use_cases.UseCaseResult` retornado.

        Args:
            scenario: Configuração do cenário (multiplicador de carga).

        Returns:
            Dicionário com as métricas brutas da transação.
        """
        if self.use_case_sim is None:
            raise RuntimeError(
                "Componentes não injetados: chame set_components() antes "
                "de executar a simulação."
            )

        load = float(scenario["load_multiplier"])

        # Sorteia o caso de uso conforme a distribuição configurada.
        uc = str(np.random.choice(self._uc_keys, p=self._uc_probs))
        
        # Executa o caso de uso REAL através das cinco camadas. Quando há
        # dataset, os parâmetros (produto, CEPs, pedido) são sorteados do
        # Olist; sem dataset, usa-se uma carga sintética equivalente.
        if self.dataset is not None:
            result = self.use_case_sim.execute(uc, load_multiplier=load)
        else:
            result = self._execute_without_dataset(uc, load)

        latency_end_to_end = float(result.latency_ms)
        # Tempo de tradução semântica = overhead da camada de
        # interoperabilidade (camada 3) desta transação.
        translation_time = float(
            result.layer_overhead_ms.get("interoperabilidade", 0.0)
        )
        translation_occurred = result.n_translations > 0

        # Erro de tradução: probabilístico, proporcional ao número de
        # traduções e à taxa de erro configurada no mediador.
        translation_error = False
        if translation_occurred:
            err_rate = float(
                getattr(self.semantic_mediator, "translation_error_rate", 0.0)
            )
            p_err = 1.0 - (1.0 - err_rate) ** result.n_translations
            translation_error = bool(np.random.random() < p_err)

        # Rejeição por sobrecarga: cresce com o multiplicador de carga.
        rej_base = self.sim_config["loading_rejection_prob_base"]
        rejection_prob = min(0.1, rej_base * load)
        load_rejected = bool(np.random.random() < rejection_prob)
         
        timeout = latency_end_to_end > float(
            self.sim_config["timeout_threshold"]
        )
        success = (
            result.success
            and not load_rejected
            and not timeout
            and not translation_error
        )
        rejected = load_rejected or not result.success

        return {
            "use_case": uc,
            "latency_end_to_end": latency_end_to_end,
            "latency_translation": translation_time,
            "translation_occurred": bool(translation_occurred),
            "translation_error": translation_error,
            "cache_hit": bool(result.cache_hit),
            "success": success,
            "rejected": rejected,
            "timeout": timeout,
        }

    # ------------------------------------------------------------------
    def _execute_without_dataset(
        self, uc: str, load: float
    ) -> Any:
        """Executa um caso de uso sem dataset (carga sintética).

        Fornece parâmetros sintéticos equivalentes aos do Olist para que os
        casos de uso possam ser executados de ponta a ponta mesmo sem os
        arquivos CSV reais disponíveis, preservando a estrutura de chamadas
        às cinco camadas.

        Args:
            uc: ``uc1`` | ``uc2`` | ``uc3``.
            load: Multiplicador de carga do cenário.

        Returns:
            :class:`~src.simulation.use_cases.UseCaseResult`.
        """
        sim = self.use_case_sim
        if uc == "uc1":
            return sim.execute_uc1_consultar_produto(
                product_id="PROD-SINTETICO", quantity=1, load_multiplier=load
            )
        if uc == "uc2":
            seller_zip = int(self.rng.randint(1000, 99999))
            customer_zip = int(self.rng.randint(1000, 99999))
            peso = round(self.rng.uniform(0.3, 12.0), 2)
            return sim.execute_uc2_calcular_entrega(
                seller_zip=seller_zip,
                customer_zip=customer_zip,
                peso_kg=peso,
                load_multiplier=load,
            )
        # uc3 — pedido sintético (itens sem product_id evitam a verificação
        # de estoque aleatória, garantindo a execução ponta a ponta).
        pedido_data = {
            "customer_id": f"cliente-{self.rng.randint(1, 10**6)}",
            "seller_zip": int(self.rng.randint(1000, 99999)),
            "customer_zip": int(self.rng.randint(1000, 99999)),
            "total_weight_kg": round(self.rng.uniform(0.3, 12.0), 2),
            "items": [
                {"weight_g": int(self.rng.randint(200, 8000)), "price": 99.9}
            ],
        }
        return sim.execute_uc3_processar_pedido(
            pedido_data=pedido_data, load_multiplier=load
        )

    # ------------------------------------------------------------------
    def _calculate_metrics(
        self,
        latencies_e2e: List[float],
        latencies_trans: List[float],
        trans_count: int,
        cache_hits: int,
        use_case_counts: Dict[str, int],
        msg_counts: Dict[str, int],
        timestamps: List[float],
        duration: float,
        scenario: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Calcula todas as métricas especificadas (A–E)."""
        arr_e2e = np.array(latencies_e2e) if latencies_e2e else np.array([0.0])
        arr_trans = np.array(latencies_trans) if latencies_trans else np.array([0.0])
        total = msg_counts["total"]

        return {
            "scenario": scenario["name"],

            # A) Latência fim-a-fim
            "latency_e2e_mean": float(np.mean(arr_e2e)),
            "latency_e2e_median": float(np.median(arr_e2e)),
            "latency_e2e_std": float(np.std(arr_e2e)),
            "latency_e2e_p50": float(np.percentile(arr_e2e, 50)),
            "latency_e2e_p95": float(np.percentile(arr_e2e, 95)),
            "latency_e2e_p99": float(np.percentile(arr_e2e, 99)),

            # B) Latência de tradução
            "translation_time_mean": float(np.mean(arr_trans)),
            "translation_rate": trans_count / total if total > 0 else 0.0,
            "translation_overhead_mean": (
                float(np.mean(arr_trans)) * 0.70 if len(arr_trans) > 0 else 0.0
            ),

            # C) Throughput
            "throughput_mean": total / duration if duration > 0 else 0.0,
            "throughput_max": self._calculate_max_throughput(timestamps),
            "rejection_rate": (
                msg_counts["rejection"] / total if total > 0 else 0.0
            ),

            # D) Confiabilidade
            "success_rate": msg_counts["success"] / total if total > 0 else 0.0,
            "timeout_rate": msg_counts["timeout"] / total if total > 0 else 0.0,
            "translation_error_rate": (
                msg_counts["translation_error"] / trans_count
                if trans_count > 0
                else 0.0
            ),

            # E) Cache semântico (observado)
            "cache_hit_rate_observed": (
                cache_hits / trans_count if trans_count > 0 else 0.0
            ),
            "cache_miss_rate_observed": (
                (trans_count - cache_hits) / trans_count if trans_count > 0 else 0.0
            ),

            # Distribuição dos casos de uso executados
            "use_case_distribution": dict(use_case_counts),

            # Dados brutos
            "latencies_raw": arr_e2e.tolist(),
            "duration": duration,
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _calculate_max_throughput(timestamps: List[float]) -> float:
        """Calcula o throughput máximo em uma janela de 1 segundo."""
        if len(timestamps) < 2:
            return 0.0
        ts = np.array(timestamps)
        window = 1.0
        max_tput = 0
        # Amostragem para evitar O(n²) em arrays grandes
        step = max(1, len(ts) // 500)
        for i in range(0, len(ts), step):
            window_end = ts[i] + window
            count = int(np.sum((ts >= ts[i]) & (ts < window_end)))
            max_tput = max(max_tput, count)
        return float(max_tput)

    # ------------------------------------------------------------------
    def run_cache_sensitivity_analysis(
        self, scenario_key: str = "normal"
    ) -> Dict[str, Dict[str, Any]]:
        """Análise de Sensibilidade do Cache do Semantic Mediator.

        Testa as taxas de acerto de cache configuradas (0 %, 50 %, 80 %,
        95 %) no cenário-base e calcula o ganho de latência e a economia
        no tempo de tradução em relação ao cache frio (0 %).

        Args:
            scenario_key: Cenário-base para a análise (padrão: ``normal``).

        Returns:
            Dicionário ``{taxa_str: métricas}``.
        """
        cache_rates = list(self.interop["cache_hit_rates"])
        results: Dict[str, Dict[str, Any]] = {}

        print(f"\n{'=' * 70}")
        print("ANÁLISE DE SENSIBILIDADE DO CACHE")
        print(f"{'=' * 70}")

        for cache_rate in cache_rates:
            print(f"\nCache Hit Rate: {cache_rate * 100:.0f}%")
            # Ajusta a taxa de acerto no modelo de overhead E no mediador
            # semântico (camada 3) usados pelos casos de uso reais.
            if self.use_case_sim is not None:
                self.use_case_sim.configure_cache(cache_rate)
            else:
                self.semantic_mediator.set_cache_hit_rate(cache_rate)

            result = self.run_scenario(scenario_key)

            results[f"{cache_rate * 100:.0f}%"] = {
                "cache_hit_rate": cache_rate,
                "latency_mean": result["latency_e2e_mean"],
                "translation_time_mean": result["translation_time_mean"],
                # E) Cache (taxas observadas a partir das transações reais)
                "cache_hit_rate_observed": result["cache_hit_rate_observed"],
                "cache_miss_rate_observed": result["cache_miss_rate_observed"],
            }

        # Calcular reduções (ganho de latência e economia de tradução)
        baseline_lat = results["0%"]["latency_mean"]
        baseline_tr = results["0%"]["translation_time_mean"]
        for key, res in results.items():
            if key != "0%" and baseline_lat > 0:
                res["reduction_percent"] = round(
                    (baseline_lat - res["latency_mean"]) / baseline_lat * 100, 2
                )
                res["translation_savings_percent"] = round(
                    (baseline_tr - res["translation_time_mean"]) / baseline_tr * 100, 2
                ) if baseline_tr > 0 else 0.0
            else:
                res["reduction_percent"] = 0.0
                res["translation_savings_percent"] = 0.0

        return results


# ======================================================================
# Motor estatístico legado (compatibilidade com testes existentes)
# ======================================================================

@dataclass
class RunResult:
    """Resultado de uma única execução de simulação (motor legado)."""

    latencies_ms: List[float] = field(default_factory=list)
    transactions_completed: int = 0
    transactions_rejected: int = 0
    transactions_timeout: int = 0
    transactions_started: int = 0
    messages_total: int = 0
    sim_duration_s: float = 0.0
    deliveries_scheduled: int = 0
    layer_overhead: Dict[str, Any] = field(default_factory=dict)

    @property
    def throughput(self) -> float:
        if self.sim_duration_s <= 0:
            return 0.0
        return self.transactions_completed / self.sim_duration_s

    @property
    def rejection_rate(self) -> float:
        if self.transactions_started <= 0:
            return 0.0
        return (
            self.transactions_rejected + self.transactions_timeout
        ) / self.transactions_started


def run_simulation(
    metrics: DatasetMetrics,
    load_multiplier: float = 1.0,
    cache_hit_rate: float = 0.0,
    duration_s: float = 10.0,
    warmup_s: float = 1.0,
    n_buyers: int = 50,
    n_sellers: int = 20,
    n_mediators: int = 3,
    n_logistics: int = 5,
    seed: Optional[int] = None,
    agent_kwargs: Optional[Dict[str, Any]] = None,
    measure_layers: bool = True,
) -> RunResult:
    """Gerador estatístico de transações (compatibilidade com testes).

    .. deprecated::
        Usar :class:`SimulationEngine` para novos experimentos. Esta
        função é mantida para compatibilidade com os testes existentes.

    Args:
        metrics: Métricas derivadas do dataset Olist.
        load_multiplier: Fator de carga do cenário.
        cache_hit_rate: Taxa de acerto do cache semântico (camada 3).
        duration_s: Duração simulada (segundos).
        warmup_s: Período de aquecimento descartado dos resultados.
        n_buyers: Capacidade de geração de pedidos.
        n_sellers: Capacidade de atendimento.
        n_mediators: Capacidade de orquestração.
        n_logistics: Agentes de logística.
        seed: Semente aleatória.
        agent_kwargs: Parâmetros extras.
        measure_layers: Mede o overhead por camada se ``True``.

    Returns:
        :class:`RunResult` com dados de latência/throughput.
    """
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed % (2**31))

    rng = random.Random(seed)
    akw = agent_kwargs or {}

    processing_time_ms = float(akw.get("processing_time_ms", 150.0))
    stock_probability = float(akw.get("stock_probability", 0.85))
    patience_ms = float(akw.get("patience_ms", 3000.0))

    base_interarrival = max(1e-3, float(metrics.mean_interarrival_s))
    arrival_rate_per_s = (load_multiplier * max(n_buyers, 1)) / base_interarrival
    arrival_rate_per_s = min(arrival_rate_per_s, 5000.0)

    total_duration = warmup_s + duration_s
    expected_arrivals = int(arrival_rate_per_s * total_duration)
    expected_arrivals = max(1, min(expected_arrivals, 20000))

    capacity_per_s = (n_sellers * 1000.0 / processing_time_ms) * max(n_mediators, 1)
    capacity = max(1.0, capacity_per_s * total_duration)
    rho = expected_arrivals / capacity

    model = LayerOverheadModel(cache_hit_rate=cache_hit_rate)
    acc = LayerOverheadAccumulator()

    latencies: List[float] = []
    started = 0
    completed = 0
    rejected = 0
    timeout = 0
    deliveries = 0

    for _ in range(expected_arrivals):
        started += 1

        if rho > 1.0 and rng.random() < (1.0 - 1.0 / rho):
            rejected += 1
            continue

        service_ms = max(1.0, rng.gauss(processing_time_ms, processing_time_ms * 0.25))
        if rho < 1.0:
            wait_ms = service_ms * (rho / max(1e-3, 1.0 - rho))
        else:
            wait_ms = service_ms * rho
        wait_ms = min(wait_ms, patience_ms * 2)

        total_ov, breakdown, hit = model.total(rng)
        if measure_layers:
            acc.add(breakdown, hit)

        total_latency = service_ms + wait_ms + total_ov

        if total_latency > patience_ms:
            timeout += 1
            continue

        if rng.random() > stock_probability:
            rejected += 1
            continue

        completed += 1
        deliveries += 1
        latencies.append(total_latency)

    if warmup_s > 0 and total_duration > 0 and latencies:
        warmup_frac = warmup_s / total_duration
        skip = int(len(latencies) * warmup_frac)
        latencies = latencies[skip:]

    result = RunResult(sim_duration_s=duration_s)
    result.latencies_ms = latencies
    result.transactions_started = started
    result.transactions_completed = completed
    result.transactions_rejected = rejected
    result.transactions_timeout = timeout
    result.messages_total = started * 5
    result.deliveries_scheduled = deliveries

    if measure_layers and acc.translations > 0:
        result.layer_overhead = acc.as_dict()

    return result
