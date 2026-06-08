"""Definições de cenários de carga do experimento IIAE-BR.

Cada cenário representa um nível de carga distinto sobre a plataforma de
e-commerce, parametrizado por um **multiplicador de carga** aplicado à
taxa-base de requisições derivada do dataset Olist.

Os cenários podem ser usados de duas formas:

* **Lista padrão** (:data:`DEFAULT_SCENARIOS`) — usada pelo runner Monte
  Carlo e pelos testes;
* **Carregados da configuração** (:class:`ScenarioManager`) — lê os
  cenários diretamente de ``configs/iiae_br_config.yaml``, mantendo uma
  única fonte de verdade para os parâmetros do experimento.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import yaml

# Caminho padrão do arquivo de configuração consolidado do projeto.
DEFAULT_CONFIG_PATH = "configs/iiae_br_config.yaml"


@dataclass
class Scenario:
    """Um cenário de carga.

    Attributes:
        name: Nome do cenário (ex.: ``Normal``, ``Pico``).
        load_multiplier: Multiplicador de carga aplicado à taxa-base.
        description: Descrição textual do cenário.
        color: Cor associada ao cenário nos gráficos (opcional).
        key: Chave do cenário no arquivo de configuração (opcional).
    """

    name: str
    load_multiplier: float
    description: str = ""
    color: str = ""
    key: str = ""

    def __str__(self) -> str:
        return f"{self.name} ({self.load_multiplier}x)"


# Cenários padrão conforme o desenho do experimento.
# Normal (1x), Pico (3x), Black Friday (10x), Estresse (20x).
DEFAULT_SCENARIOS: List[Scenario] = [
    Scenario("Normal", 1.0, "Carga normal de operação (1× baseline)", "blue", "normal"),
    Scenario("Pico", 3.0, "Horário de pico (3× baseline)", "green", "pico"),
    Scenario(
        "BlackFriday", 10.0, "Evento Black Friday (10× baseline)", "yellow",
        "blackfriday",
    ),
    Scenario(
        "Estresse", 20.0, "Teste de estresse extremo (20× baseline)", "red",
        "estresse",
    ),
]


def get_scenarios_from_config(config_scenarios) -> List[Scenario]:
    """Converte objetos de cenário da configuração em :class:`Scenario`."""
    return [
        Scenario(
            name=s.name,
            load_multiplier=s.load_multiplier,
            description=getattr(s, "description", ""),
            color=getattr(s, "color", ""),
        )
        for s in config_scenarios
    ]


class ScenarioManager:
    """Gerencia os cenários de carga lidos do arquivo de configuração.

    Lê a seção ``scenarios`` de ``configs/iiae_br_config.yaml`` e expõe os
    cenários como objetos :class:`Scenario`, garantindo uma única fonte de
    verdade para os multiplicadores de carga do experimento.

    Parameters:
        config_path: Caminho do arquivo de configuração YAML.
    """

    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH) -> None:
        with open(config_path, "r", encoding="utf-8") as fh:
            config = yaml.safe_load(fh)
        self.scenarios_config: Dict[str, dict] = config.get("scenarios", {})
        self.scenarios: Dict[str, Scenario] = self._load_scenarios()

    # ------------------------------------------------------------------
    def _load_scenarios(self) -> Dict[str, Scenario]:
        """Carrega e converte os cenários da configuração em objetos."""
        scenarios: Dict[str, Scenario] = {}
        for key, cfg in self.scenarios_config.items():
            scenarios[key] = Scenario(
                key=key,
                name=cfg["name"],
                load_multiplier=float(cfg["load_multiplier"]),
                color=cfg.get("color", ""),
                description=cfg.get("description", ""),
            )
        return scenarios

    # ------------------------------------------------------------------
    def get_scenario(self, key: str) -> Scenario:
        """Retorna um cenário pela sua chave (ex.: ``normal``)."""
        if key not in self.scenarios:
            raise ValueError(f"Cenário '{key}' não encontrado")
        return self.scenarios[key]

    def get_all_scenarios(self) -> Dict[str, Scenario]:
        """Retorna todos os cenários carregados."""
        return self.scenarios

    def get_scenario_keys(self) -> List[str]:
        """Retorna a lista de chaves de cenários disponíveis."""
        return list(self.scenarios.keys())

    def as_list(self) -> List[Scenario]:
        """Retorna os cenários como uma lista de :class:`Scenario`."""
        return list(self.scenarios.values())
