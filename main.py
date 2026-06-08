#!/usr/bin/env python3
"""IIAE-BR — Experimento de Interoperabilidade de Agentes Inteligentes.

Ponto de entrada principal do experimento de simulação Monte Carlo.
Usa o :class:`~src.simulation.engine.SimulationEngine` para simular a
interação entre o **SalesAgent** (Schema.org) e o **LogisticsAgent**
(GoodRelations) através das cinco camadas da arquitetura IIAE-BR.

Uso::

    python main.py                          # todos os cenários + análise de cache
    python main.py --iterations 1000        # execução rápida
    python main.py --cache-analysis         # apenas a sensibilidade do cache
    python main.py --no-charts              # sem gerar gráficos
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from pathlib import Path

import numpy as np
import yaml



# Garante o diretório raiz do projeto no sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.chart_generator import ChartGenerator
from src.layer_1_application.logistics_agent import LogisticsAgent
from src.layer_1_application.sales_agent import SalesAgent
from src.layer_2_orchestration.load_balancer import LoadBalancer
from src.layer_2_orchestration.orchestrator import Orchestrator
from src.layer_3_interoperability.agent_registry import AgentRegistry
from src.layer_3_interoperability.semantic_mediator.mediator import SemanticMediator
from src.layer_5_infrastructure.security_gateway import SecurityGateway
from src.simulation.engine import SimulationEngine
from src.utils.data_loader import OlistDataset


def setup_logging(verbose: bool = False) -> None:
    """Configura o *logging* global do experimento."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    """Define e interpreta os argumentos de linha de comando."""
    parser = argparse.ArgumentParser(
        description="IIAE-BR — Simulação Monte Carlo",
    )
    parser.add_argument("--config", default="configs/iiae_br_config.yaml",
                        help="Caminho para o arquivo de configuração")
    parser.add_argument("--iterations", "-n", type=int, default=None,
                        help="Sobrepõe o número de iterações da config")
    parser.add_argument("--cache-analysis", action="store_true",
                        help="Executa apenas a análise de sensibilidade do cache")
    parser.add_argument("--no-charts", action="store_true",
                        help="Pula a geração de gráficos")
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser.parse_args()


def build_components(config: dict, dataset: OlistDataset, seed: int):
    """Monta os componentes reais das cinco camadas da arquitetura IIAE-BR.

    Returns:
        Tupla ``(sales, logistics, orchestrator, mediator)``.
    """
    rng = random.Random(seed)
    app_agents = config["application"]["agents"]

    # Camada 1 — Aplicação
    sales = SalesAgent(app_agents["sales"]["id"], dataset_olist=dataset, rng=rng)
    logistics = LogisticsAgent(
        app_agents["logistics"]["id"], dataset_olist=dataset, rng=rng
    )

    # Camada 3 — Interoperabilidade
    registry = AgentRegistry()
    registry.register(sales.agent_id, "sales", "schema.org",
                      ["consultar_produto", "verificar_disponibilidade",
                       "processar_pedido", "atualizar_status"])
    registry.register(logistics.agent_id, "logistics", "goodrelations",
                      ["calcular_prazo", "calcular_frete",
                       "rastrear_entrega", "notificar_status"])

    interop = config["interoperability"]["semantic_mediator"]
    mediator = SemanticMediator(
        hit_time_mean=interop["translation_time_cache_hit"]["mean"],
        hit_time_std=interop["translation_time_cache_hit"]["std"],
        miss_time_mean=interop["translation_time_cache_miss"]["mean"],
        miss_time_std=interop["translation_time_cache_miss"]["std"],
        translation_error_rate=interop["translation_error_rate"],
    )


    # Camada 2 — Orquestração
    orchestrator = Orchestrator(registry=registry, load_balancer=LoadBalancer())

    return sales, logistics, orchestrator, mediator


def _strip_raw(results: dict) -> dict:
    """Remove as latências brutas para serialização JSON enxuta."""
    clean = {}
    for key, metrics in results.items():
        clean[key] = {k: v for k, v in metrics.items() if k != "latencies_raw"}
    return clean


def main() -> None:
    """Executa o experimento de simulação Monte Carlo."""
    args = parse_args()
    setup_logging(args.verbose)
    lgr = logging.getLogger("iiae-br")
    t_global = time.time()

    print("=" * 70)
    print("IIAE-BR - Simulação Monte Carlo")
    print("Arquitetura de Interoperabilidade de Agentes Inteligentes")
    print("=" * 70)

    # 1. Configuração
    with open(args.config, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)

    seed = config.get("experiment", {}).get("seed", 42)
    random.seed(seed)
    np.random.seed(seed)

    output_cfg = config["output"]
    results_dir = output_cfg["results_dir"]
    charts_dir = output_cfg["charts_dir"]
    reports_dir = output_cfg["reports_dir"]
    for d in (results_dir, charts_dir, reports_dir):
        Path(d).mkdir(parents=True, exist_ok=True)

    # 2. Dataset Olist
    print("\nCarregando dataset Olist...")
    dataset = OlistDataset.load(PROJECT_ROOT / config["dataset"]["path"])
    resumo = dataset.summary()
    print(f"  Pedidos: {resumo.get('orders', 0)} | "
          f"Produtos: {resumo.get('products', 0)} | "
          f"CEPs: {resumo.get('geolocation_zips', 0)}")

    # Sem os CSVs do Olist disponíveis, o dataset vem vazio: a simulação
    # cai para a carga sintética equivalente (dataset=None no motor).
    dataset_disponivel = resumo.get("orders", 0) > 0 and resumo.get("products", 0) > 0
    if not dataset_disponivel:
        print("  [aviso] Dataset Olist indisponível — usando carga sintética "
              "equivalente (mesma estrutura de 5 camadas).")

    # 3. Arquitetura de 5 camadas (componentes reais)
    print("Inicializando arquitetura IIAE-BR (5 camadas)...")
    sales, logistics, orchestrator, mediator = build_components(config, dataset, seed)

    # 4. Motor de simulação
    engine = SimulationEngine(args.config)
    engine.set_components(
        sales, logistics, orchestrator, mediator,
        dataset=dataset if dataset_disponivel else None,
    )
    if args.iterations is not None:
        engine.sim_config["iterations"] = args.iterations
    print(f"Iterações por cenário: {engine.sim_config['iterations']}")

    # 5. Execução
    if args.cache_analysis:
        cache_results = engine.run_cache_sensitivity_analysis()
        print("\nResultados:")
        for key, value in cache_results.items():
            print(f"\n{key}:")
            print(f"  Latência Média: {value['latency_mean']:.2f} ms")
            print(f"  Redução: {value.get('reduction_percent', 0.0):.2f}%")
        with open(f"{reports_dir}/cache_sensitivity.json", "w", encoding="utf-8") as f:
            json.dump(cache_results, f, indent=2, ensure_ascii=False)
        lgr.info("Tempo total: %.1fs", time.time() - t_global)
        return

    print("\nExecutando simulação em todos os cenários...")
    results = engine.run_all_scenarios()

    print("\nExecutando análise de sensibilidade do cache...")
    cache_results = engine.run_cache_sensitivity_analysis()

    # 6. Gráficos e tabelas
    if not args.no_charts:
        print("\nGerando gráficos e relatórios...")
        chart_gen = ChartGenerator(config)
        chart_gen.generate_all_charts(results, cache_results, charts_dir)

    # 7. Salvar resultados
    with open(f"{reports_dir}/simulation_results.json", "w", encoding="utf-8") as f:
        json.dump(_strip_raw(results), f, indent=2, ensure_ascii=False, default=str)
    with open(f"{reports_dir}/cache_sensitivity.json", "w", encoding="utf-8") as f:
        json.dump(cache_results, f, indent=2, ensure_ascii=False, default=str)

    # 8. Resumo
    print("\n" + "=" * 70)
    print("RESUMO DOS RESULTADOS")
    print("=" * 70)
    for scenario, metrics in results.items():
        print(f"\n{metrics['scenario']}:")
        print(f"  Latência Média: {metrics['latency_e2e_mean']:.2f} ms "
              f"(p95={metrics['latency_e2e_p95']:.2f} ms)")
        print(f"  Throughput:     {metrics['throughput_mean']:.2f} msg/s")
        print(f"  Taxa Sucesso:   {metrics['success_rate'] * 100:.2f}%")
        print(f"  Taxa Rejeição:  {metrics['rejection_rate'] * 100:.2f}%")

    print("\n" + "=" * 70)
    print("Simulação concluída!")
    print(f"Resultados salvos em: {reports_dir}")
    if not args.no_charts:
        print(f"Gráficos salvos em:   {charts_dir}")
    print(f"Tempo total: {time.time() - t_global:.1f}s")
    print("=" * 70)


if __name__ == "__main__":
    main()
