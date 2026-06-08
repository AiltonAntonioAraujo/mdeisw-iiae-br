"""Gerador de Gráficos Específicos para o Experimento IIAE-BR.

Gera **exatamente seis gráficos** e uma tabela, conforme a especificação
do estudo, a partir dos resultados produzidos pelo
:class:`~src.simulation.engine.SimulationEngine`:

#. Taxa de rejeição por cenário (SLA < 1,0 %);
#. Latência do Semantic Mediator por cenário (cores por cenário);
#. Taxa de sucesso por cenário (SLA > 99,9 %);
#. Latência fim-a-fim por cenário (SLA < 150 ms);
#. Throughput médio por cenário (SLA > 1000 msg/s);
#. Histograma da distribuição da latência (0–250 ms, bins de 50 ms).

Além disso, gera a **tabela de sensibilidade do cache** (Cache Hit,
Latência Média, Redução %) em CSV e PNG.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import matplotlib

matplotlib.use("Agg")  # backend não-interativo (execução headless)

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.patches import Patch


class ChartGenerator:
    """Gera os seis gráficos especificados e a tabela de cache.

    Parameters:
        config: Configuração do experimento (dicionário do YAML), contendo
            as seções ``slas`` e ``scenarios``.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.slas = config["slas"]
        self.scenarios = config["scenarios"]
        sns.set_style("whitegrid")

    # ------------------------------------------------------------------
    def _ensure_dir(self, path: str) -> None:
        os.makedirs(path, exist_ok=True)

    def _name(self, key: str) -> str:
        """Nome amigável do cenário a partir da chave."""
        return self.scenarios.get(key, {}).get("name", key)

    def _color(self, key: str) -> str:
        """Cor configurada do cenário (com fallback)."""
        return self.scenarios.get(key, {}).get("color", "steelblue")

    # ------------------------------------------------------------------
    def generate_all_charts(
        self,
        results: Dict[str, Dict[str, Any]],
        cache_analysis: Dict[str, Dict[str, Any]],
        output_dir: str,
    ) -> None:
        """Gera todos os seis gráficos e a tabela de sensibilidade."""
        self._ensure_dir(output_dir)
        reports_dir = self.config.get("output", {}).get(
            "reports_dir", str(Path(output_dir).parent / "reports")
        )
        self._ensure_dir(reports_dir)

        self.plot_rejection_rate(results, output_dir)
        self.plot_semantic_mediator_latency(results, output_dir)
        self.plot_success_rate(results, output_dir)
        self.plot_end_to_end_latency(results, output_dir)
        self.plot_throughput(results, output_dir)
        self.plot_latency_distribution_histogram(results, output_dir)
        self.generate_cache_sensitivity_table(cache_analysis, output_dir, reports_dir)

    # ------------------------------------------------------------------
    # Gráfico 1 — Taxa de rejeição por cenário
    # ------------------------------------------------------------------
    def plot_rejection_rate(self, results, output_dir) -> None:
        """Gráfico 1: Taxa de rejeição por cenário (SLA < 0,1 %)."""
        fig, ax = plt.subplots(figsize=(10, 6))
        labels = [self._name(s) for s in results]
        rejection_rates = [results[s]["rejection_rate"] * 100 for s in results]

        bars = ax.bar(labels, rejection_rates, color="steelblue", alpha=0.75,
                      edgecolor="black")

        sla_value = self.slas["rejection_rate"] * 100
        ax.axhline(y=sla_value, color="red", linestyle="--",
                   label=f"SLA < {sla_value:.1f}%", linewidth=2)
        ax.bar_label(bars, fmt="%.2f%%", padding=3, fontsize=10)

        for bar, rate in zip(bars, rejection_rates):
            if rate > sla_value:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        rate + max(rejection_rates) * 0.04,
                        "VIOLA SLA", ha="center", va="bottom",
                        color="red", fontweight="bold", fontsize=9)

        ax.set_ylabel("Taxa de Rejeição (%)", fontsize=12)
        ax.set_title("Taxa de Rejeição por Cenário", fontsize=14, fontweight="bold")
        ax.legend()
        plt.tight_layout()
        plt.savefig(f"{output_dir}/1_taxa_rejeicao_por_cenario.png", dpi=300)
        plt.close(fig)

    # ------------------------------------------------------------------
    # Gráfico 2 — Latência do Semantic Mediator por cenário
    # ------------------------------------------------------------------
    def plot_semantic_mediator_latency(self, results, output_dir) -> None:
        """Gráfico 2: Latência do Semantic Mediator por cenário."""
        fig, ax = plt.subplots(figsize=(10, 6))
        labels = [self._name(s) for s in results]
        latencies = [results[s]["translation_time_mean"] for s in results]
        colors = [self._color(s) for s in results]

        bars = ax.bar(labels, latencies, color=colors, alpha=0.75, edgecolor="black")
        ax.bar_label(bars, fmt="%.2f ms", padding=3, fontsize=10)
        ax.set_ylabel("Latência (ms)", fontsize=12)
        ax.set_title("Latência do Semantic Mediator por Cenário",
                     fontsize=14, fontweight="bold")
        plt.tight_layout()
        plt.savefig(f"{output_dir}/2_latencia_semantic_mediator.png", dpi=300)
        plt.close(fig)

    # ------------------------------------------------------------------
    # Gráfico 3 — Taxa de sucesso por cenário
    # ------------------------------------------------------------------
    def plot_success_rate(self, results, output_dir) -> None:
        """Gráfico 3: Taxa de sucesso por cenário (SLA > 99,9 %)."""
        fig, ax = plt.subplots(figsize=(10, 6))
        labels = [self._name(s) for s in results]
        success_rates = [results[s]["success_rate"] * 100 for s in results]

        sla_value = self.slas["success_rate"] * 100
        colors = ["blue" if rate >= sla_value else "lightcoral"
                  for rate in success_rates]

        bars = ax.bar(labels, success_rates, color=colors, alpha=0.75, edgecolor="black")
        ax.bar_label(bars, fmt="%.2f%%", padding=3, fontsize=10)

        ax.axhline(y=sla_value, color="red", linestyle="--",
                   label=f"SLA > {sla_value:.1f}%", linewidth=2)

        ax.set_ylabel("Taxa de Sucesso (%)", fontsize=12)
        ax.set_title("Taxa de Sucesso por Cenário", fontsize=14, fontweight="bold")
        ax.set_ylim(0, 105)
        ax.legend()
        plt.tight_layout()
        plt.savefig(f"{output_dir}/3_taxa_sucesso_por_cenario.png", dpi=300)
        plt.close(fig)

    # ------------------------------------------------------------------
    # Gráfico 4 — Latência fim-a-fim por cenário
    # ------------------------------------------------------------------
    def plot_end_to_end_latency(self, results, output_dir) -> None:
        """Gráfico 4: Latência fim-a-fim por cenário (SLA < 150 ms)."""
        fig, ax = plt.subplots(figsize=(10, 6))
        labels = [self._name(s) for s in results]
        latencies = [results[s]["latency_e2e_mean"] for s in results]

        sla_value = self.slas["latency_end_to_end"]
        colors = ["blue" if lat <= sla_value else "lightcoral" for lat in latencies]

        bars = ax.bar(labels, latencies, color=colors, alpha=0.75, edgecolor="black")
        ax.bar_label(bars, fmt="%.2f ms", padding=3, fontsize=10)
        ax.axhline(y=sla_value, color="red", linestyle="--",
                   label=f"SLA < {sla_value:.0f} ms", linewidth=2)

        ax.set_ylabel("Latência (ms)", fontsize=12)
        ax.set_title("Latência Fim-a-Fim por Cenário", fontsize=14, fontweight="bold")
        ax.legend()
        plt.tight_layout()
        plt.savefig(f"{output_dir}/4_latencia_fim_a_fim.png", dpi=300)
        plt.close(fig)

    # ------------------------------------------------------------------
    # Gráfico 5 — Throughput médio por cenário
    # ------------------------------------------------------------------
    def plot_throughput(self, results, output_dir) -> None:
        """Gráfico 5: Throughput médio por cenário (SLA > 1000 msg/s)."""
        fig, ax = plt.subplots(figsize=(10, 6))
        labels = [self._name(s) for s in results]
        throughputs = [results[s]["throughput_mean"] for s in results]
        colors = [self._color(s) for s in results]

        bars = ax.bar(labels, throughputs, color=colors, alpha=0.75, edgecolor="black")
        ax.bar_label(bars, fmt="%.2f msg/s", padding=3, fontsize=10)
        sla_value = self.slas["throughput_min"]
        ax.axhline(y=sla_value, color="red", linestyle="--",
                   label=f"SLA > {sla_value:.0f} msg/s", linewidth=2)

        for bar, tput in zip(bars, throughputs):
            if tput < sla_value:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        tput + max(throughputs) * 0.02,
                        "VIOLA SLA", ha="center", va="bottom",
                        color="red", fontweight="bold", fontsize=9)

        ax.set_ylabel("Throughput (msg/s)", fontsize=12)
        ax.set_title("Throughput Médio por Cenário", fontsize=14, fontweight="bold")
        ax.legend()
        plt.tight_layout()
        plt.savefig(f"{output_dir}/5_throughput_medio.png", dpi=300)
        plt.close(fig)

    # ------------------------------------------------------------------
    # Gráfico 6 — Histograma da distribuição da latência
    # ------------------------------------------------------------------
    def plot_latency_distribution_histogram(self, results, output_dir) -> None:
        """Gráfico 6: Histograma da distribuição da latência fim-a-fim."""
        fig, ax = plt.subplots(figsize=(12, 7))

        all_latencies = []
        for scenario in results.values():
            all_latencies.extend(scenario["latencies_raw"])
        all_latencies = np.array(all_latencies)
        total = max(1, len(all_latencies))

        bins = [0, 50, 100, 150, 200, 250]
        counts, _ = np.histogram(all_latencies, bins=bins)
        percentages = (counts / total) * 100

        colors_by_bin = []
        for edge in bins[:-1]:
            if edge < 150:
                colors_by_bin.append("green")
            elif edge < 200:
                colors_by_bin.append("yellow")
            else:
                colors_by_bin.append("red")

        x_pos = range(len(bins) - 1)
        bars = ax.bar(x_pos, percentages, color=colors_by_bin, alpha=0.75,
               edgecolor="black", linewidth=1.5)
        ax.bar_label(bars, fmt="%.1f%%", padding=3, fontsize=10)
        
        sla_value = self.slas["latency_end_to_end"]
        sla_pos = 3  # fronteira 150 ms (índice do bin 150-200)
        ax.axvline(x=sla_pos - 0.5, color="red", linestyle="--",
                   label=f"SLA < {sla_value:.0f} ms", linewidth=2)

        within_sla = int(np.sum(all_latencies < sla_value))
        pct_within_sla = (within_sla / total) * 100
        ax.text(0.02, 0.85,
                f"{pct_within_sla:.1f}% das requisições\natendem o SLA",
                transform=ax.transAxes, ha="left", va="top",
                bbox=dict(boxstyle="round", facecolor="white", alpha=0.85),
                fontsize=11, fontweight="bold")

        ax.set_xticks(list(x_pos))
        ax.set_xticklabels([f"{bins[i]}-{bins[i+1]}" for i in range(len(bins) - 1)])
        ax.set_xlabel("Faixa de Latência (ms)", fontsize=12)
        ax.set_ylabel("Frequência (%)", fontsize=12)
        ax.set_title("Distribuição da Latência Fim-a-Fim",
                     fontsize=14, fontweight="bold")

        legend_elements = [
            Patch(facecolor="green", alpha=0.75, label="< 150 ms (SLA)"),
            Patch(facecolor="yellow", alpha=0.75, label="150-200 ms (Atenção)"),
            Patch(facecolor="red", alpha=0.75, label="> 200 ms (Crítico)"),
        ]
        ax.legend(handles=legend_elements, loc="upper right")
        plt.tight_layout()
        plt.savefig(f"{output_dir}/6_histograma_distribuicao_latencia.png", dpi=300)
        plt.close(fig)

    # ------------------------------------------------------------------
    # Tabela — Sensibilidade do cache
    # ------------------------------------------------------------------
    def generate_cache_sensitivity_table(
        self, cache_analysis, output_dir, reports_dir
    ) -> None:
        """Gera a tabela de análise de sensibilidade do cache (CSV + PNG)."""
        data = []
        for key, value in cache_analysis.items():
            data.append({
                "Taxa de Cache Hit": key,
                "Latência Média (ms)": f"{value['latency_mean']:.2f}",
                "Redução (%)": f"{value.get('reduction_percent', 0.0):.2f}",
            })
        df = pd.DataFrame(data)

        self._ensure_dir(reports_dir)
        df.to_csv(f"{reports_dir}/tabela_sensibilidade_cache.csv", index=False)

        fig, ax = plt.subplots(figsize=(10, 4))
        ax.axis("tight")
        ax.axis("off")
        table = ax.table(cellText=df.values, colLabels=df.columns,
                         cellLoc="center", loc="center",
                         colWidths=[0.3, 0.35, 0.35])
        table.auto_set_font_size(False)
        table.set_fontsize(11)
        table.scale(1, 2)
        for i in range(len(df.columns)):
            table[(0, i)].set_facecolor("#4CAF50")
            table[(0, i)].set_text_props(weight="bold", color="white")

        plt.title("Análise de Sensibilidade do Semantic Mediator",
                  fontsize=14, fontweight="bold", pad=20)
        plt.savefig(f"{output_dir}/tabela_sensibilidade_cache.png",
                    dpi=300, bbox_inches="tight")
        plt.close(fig)
