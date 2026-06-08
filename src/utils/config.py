"""Configuration loader for the IIAE-BR experiment.

Reads YAML configuration files and provides typed access to all
experiment parameters.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import yaml


@dataclass
class AgentConfig:
    """Configuration for a specific agent type."""
    count: int = 10
    extras: Dict[str, Any] = field(default_factory=dict)

    def __getattr__(self, name: str) -> Any:
        try:
            return self.extras[name]
        except KeyError:
            raise AttributeError(f"AgentConfig has no attribute '{name}'")


@dataclass
class ScenarioConfig:
    """Configuration for a load scenario."""
    name: str
    load_multiplier: float
    description: str = ""


@dataclass
class ExperimentConfig:
    """Top-level experiment configuration."""

    name: str = "IIAE-BR"
    seed: int = 42
    monte_carlo_iterations: int = 10_000

    data_path: str = "data/"
    data_files: Dict[str, str] = field(default_factory=dict)

    agents: Dict[str, AgentConfig] = field(default_factory=dict)
    scenarios: List[ScenarioConfig] = field(default_factory=list)
    cache_levels: List[float] = field(default_factory=lambda: [0.0, 0.5, 0.8, 0.95])

    simulation_duration: float = 300.0
    warmup_seconds: float = 30.0

    output_dir: str = "results/"
    csv_dir: str = "results/csv/"
    json_dir: str = "results/json/"
    charts_dir: str = "results/charts/"
    report_file: str = "results/relatorio_final.txt"

    latency_percentiles: List[int] = field(default_factory=lambda: [50, 95, 99])
    confidence_level: float = 0.95


def load_config(config_path: str | Path | None = None) -> ExperimentConfig:
    """Load experiment configuration from a YAML file.

    Args:
        config_path: Path to YAML config. Defaults to
                     ``configs/iiae_br_config.yaml`` relative to the project root.

    Returns:
        Populated :class:`ExperimentConfig` instance.
    """
    if config_path is None:
        project_root = Path(__file__).resolve().parent.parent.parent
        config_path = project_root / "configs" / "iiae_br_config.yaml"
    else:
        config_path = Path(config_path)

    with open(config_path, "r", encoding="utf-8") as fh:
        raw: Dict[str, Any] = yaml.safe_load(fh)

    exp = raw.get("experiment", {})
    data_section = raw.get("data", {})
    agents_section = raw.get("agents", {})
    scenarios_section = raw.get("scenarios", [])
    cache_section = raw.get("cache", {})
    results_section = raw.get("results", {})
    metrics_section = raw.get("metrics", {})
    sim_section = raw.get("simulation", {})

    # Build agent configs
    agents: Dict[str, AgentConfig] = {}
    for agent_type, params in agents_section.items():
        count = params.pop("count", 10)
        agents[agent_type] = AgentConfig(count=count, extras=params)

    # Build scenario configs (aceita lista OU dicionário no YAML)
    if isinstance(scenarios_section, dict):
        scenario_items = list(scenarios_section.values())
    else:
        scenario_items = list(scenarios_section)
    scenarios = [
        ScenarioConfig(
            name=s["name"],
            load_multiplier=s["load_multiplier"],
            description=s.get("description", ""),
        )
        for s in scenario_items
    ]

    # Data files
    data_path = data_section.pop("path", "data/")
    data_files = {k: v for k, v in data_section.items()}

    cfg = ExperimentConfig(
        name=exp.get("name", "IIAE-BR"),
        seed=exp.get("seed", 42),
        monte_carlo_iterations=exp.get("monte_carlo_iterations", 10_000),
        data_path=data_path,
        data_files=data_files,
        agents=agents,
        scenarios=scenarios,
        cache_levels=cache_section.get("sensitivity_levels", [0.0, 0.5, 0.6, 0.8, 0.95]),
        simulation_duration=sim_section.get("duration_seconds", 300.0),
        warmup_seconds=sim_section.get("warmup_seconds", 30.0),
        output_dir=results_section.get("output_dir", "results/"),
        csv_dir=results_section.get("csv_dir", "results/csv/"),
        json_dir=results_section.get("json_dir", "results/json/"),
        charts_dir=results_section.get("charts_dir", "results/charts/"),
        report_file=results_section.get("report_file", "results/relatorio_final.txt"),
        latency_percentiles=metrics_section.get("latency_percentiles", [50, 95, 99]),
        confidence_level=metrics_section.get("confidence_level", 0.95),
    )
    return cfg
