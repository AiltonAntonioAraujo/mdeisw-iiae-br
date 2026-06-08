"""Layer Overhead Model — instrumentação da simulação IIAE-BR.

Modela e **mede o overhead de processamento de cada uma das 5 camadas**
da arquitetura IIAE-BR para cada transação processada. Cada camada
adiciona um custo de processamento (em milissegundos) ao percurso de uma
mensagem; o custo da **camada 3 (Interoperabilidade)** depende da taxa de
acerto do cache semântico, refletindo o overhead da tradução
Schema.org ↔ GoodRelations.

Os valores são calibrados para refletir, em ordem de grandeza, o custo
relativo de cada camada (a aplicação domina; infraestrutura é marginal),
mantendo a latência total compatível com os resultados do experimento.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, Optional

from src.layer_3_interoperability.semantic_mediator.ontology_mapper import (
    DEFAULT_HIT_COST_MS,
    DEFAULT_MISS_COST_MS,
)

# Nomes das camadas (do topo para a base)
LAYER_NAMES = (
    "aplicacao",        # Camada 1
    "orquestracao",     # Camada 2
    "interoperabilidade",  # Camada 3
    "comunicacao",      # Camada 4
    "infraestrutura",   # Camada 5
)

# Custos-base de processamento por camada (ms), exceto interoperabilidade
# que é calculada dinamicamente em função do cache semântico.
BASE_OVERHEAD_MS: Dict[str, float] = {
    "aplicacao": 0.0,        # custo da lógica de negócio já modelado nos agentes 
    "orquestracao": 0.25,    # roteamento + balanceamento + gestão de conversa 0.25
    "comunicacao": 0.30,     # serialização JSON-LD + transporte 0.30
    "infraestrutura": 0.05,  # logging + monitoramento + segurança 0.05
}

# Jitter relativo aplicado a cada custo (variabilidade realista)
JITTER = 30 # 0.30


@dataclass
class LayerOverheadAccumulator:
    """Acumula o overhead medido por camada ao longo da simulação."""

    totals_ms: Dict[str, float] = field(
        default_factory=lambda: {name: 0.0 for name in LAYER_NAMES}
    )
    counts: Dict[str, int] = field(
        default_factory=lambda: {name: 0 for name in LAYER_NAMES}
    )
    translations: int = 0
    cache_hits: int = 0
    cache_misses: int = 0

    def add(self, breakdown: Dict[str, float], hit: bool) -> None:
        for name, value in breakdown.items():
            self.totals_ms[name] += value
            self.counts[name] += 1
        self.translations += 1
        if hit:
            self.cache_hits += 1
        else:
            self.cache_misses += 1

    def avg_per_layer(self) -> Dict[str, float]:
        return {
            name: (self.totals_ms[name] / self.counts[name])
            if self.counts[name] else 0.0
            for name in LAYER_NAMES
        }

    @property
    def total_overhead_ms(self) -> float:
        return sum(self.totals_ms.values())

    @property
    def avg_total_overhead_ms(self) -> float:
        n = self.counts["interoperabilidade"]
        return self.total_overhead_ms / n if n else 0.0

    @property
    def hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total else 0.0

    def as_dict(self) -> Dict[str, object]:
        return {
            "avg_per_layer_ms": {k: round(v, 4) for k, v in self.avg_per_layer().items()},
            "total_per_layer_ms": {k: round(v, 4) for k, v in self.totals_ms.items()},
            "avg_total_overhead_ms": round(self.avg_total_overhead_ms, 4),
            "translations": self.translations,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate": round(self.hit_rate, 4),
        }


class LayerOverheadModel:
    """Calcula o overhead por camada de uma transação.

    Parameters
    ----------
    cache_hit_rate:
        Taxa de acerto do cache semântico (camada 3). Define
        probabilisticamente se a tradução de uma transação é um acerto
        (custo baixo) ou um erro de cache (tradução efetiva).
    miss_cost_ms / hit_cost_ms:
        Custos da tradução semântica em *miss* e *hit*.
    """

    def __init__(
        self,
        cache_hit_rate: float = 0.0,
        miss_cost_ms: float = DEFAULT_MISS_COST_MS,
        hit_cost_ms: float = DEFAULT_HIT_COST_MS,
    ) -> None:
        self.cache_hit_rate = cache_hit_rate
        self.miss_cost_ms = miss_cost_ms
        self.hit_cost_ms = hit_cost_ms

    # ------------------------------------------------------------------
    def sample(self, rng: random.Random) -> tuple[Dict[str, float], bool]:
        """Amostra o overhead por camada de uma transação.

        Retorna ``(breakdown, hit)`` onde ``breakdown`` mapeia o nome da
        camada para seu overhead (ms) e ``hit`` indica se a tradução foi
        servida pelo cache.
        """
        breakdown: Dict[str, float] = {}
        for name, base in BASE_OVERHEAD_MS.items():
            breakdown[name] = self._jitter(base, rng)

        # Camada 3: protocolo (constante) + tradução semântica (cache)
        protocol_cost = self._jitter(0.40, rng)
        hit = rng.random() < self.cache_hit_rate
        translation_cost = self.hit_cost_ms if hit else self.miss_cost_ms
        translation_cost = self._jitter(translation_cost, rng)
        breakdown["interoperabilidade"] = protocol_cost + translation_cost
        return breakdown, hit

    def total(self, rng: random.Random) -> tuple[float, Dict[str, float], bool]:
        """Retorna ``(total_ms, breakdown, hit)`` de uma transação."""
        breakdown, hit = self.sample(rng)
        return sum(breakdown.values()), breakdown, hit

    @staticmethod
    def _jitter(value: float, rng: random.Random) -> float:
        if value <= 0:
            return 0.0
        return max(0.0, value * (1.0 + rng.uniform(-JITTER, JITTER)))
