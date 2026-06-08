"""Load Balancer — Camada 2 (Orquestração) do IIAE-BR.

Distribui a carga de mensagens entre múltiplas instâncias de agentes de
um mesmo papel. Versão simplificada com estratégia padrão **round-robin**
e alternativa por **menor carga** (*least-loaded*), suficiente para os
cenários de simulação (carga normal, pico, Black Friday e estresse).
"""

from __future__ import annotations

from collections import defaultdict
from itertools import cycle
from typing import Dict, List, Optional

from src.layer_5_infrastructure.logging_service import get_logger

logger = get_logger(__name__)


class LoadBalancer:
    """Balanceador de carga entre instâncias de agentes."""

    def __init__(self, strategy: str = "round_robin") -> None:
        self.strategy = strategy
        self._pools: Dict[str, List[str]] = {}
        self._cyclers: Dict[str, cycle] = {}
        self._load: Dict[str, int] = defaultdict(int)
        self.dispatched = 0

    # ------------------------------------------------------------------
    def register_pool(self, role: str, agents: List[str]) -> None:
        """Registra o conjunto de instâncias de um papel."""
        self._pools[role] = list(agents)
        self._cyclers[role] = cycle(self._pools[role])
        for a in agents:
            self._load.setdefault(a, 0)

    def select(self, role: str) -> Optional[str]:
        """Seleciona uma instância do papel conforme a estratégia."""
        pool = self._pools.get(role)
        if not pool:
            return None
        if self.strategy == "least_loaded":
            agent = min(pool, key=lambda a: self._load[a])
        else:  # round_robin (padrão)
            agent = next(self._cyclers[role])
        self._load[agent] += 1
        self.dispatched += 1
        return agent

    def release(self, agent: str) -> None:
        """Sinaliza que um agente concluiu o processamento (libera carga)."""
        if self._load[agent] > 0:
            self._load[agent] -= 1

    # ------------------------------------------------------------------
    def load_snapshot(self) -> Dict[str, int]:
        return dict(self._load)

    def summary(self) -> Dict[str, int]:
        return {"dispatched": self.dispatched, "pools": len(self._pools)}
