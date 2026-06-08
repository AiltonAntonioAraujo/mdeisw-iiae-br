"""Monitoring Service — Camada 5 (Infraestrutura) do IIAE-BR.

Coleta métricas básicas da arquitetura: contadores de mensagens,
tempos de processamento por camada, health checks simples e
estatísticas agregadas.

O serviço é central para a medição de *overhead por camada*, um dos
objetivos do experimento IIAE-BR.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class LayerMetrics:
    """Métricas acumuladas de uma camada."""

    name: str
    message_count: int = 0
    error_count: int = 0
    total_time_ms: float = 0.0
    overhead_samples_ms: List[float] = field(default_factory=list)

    @property
    def mean_overhead_ms(self) -> float:
        if not self.overhead_samples_ms:
            return 0.0
        return sum(self.overhead_samples_ms) / len(self.overhead_samples_ms)


class MonitoringService:
    """Serviço de monitoramento e coleta de métricas.

    Mantém contadores e tempos por camada e por tipo de evento. Suporta
    health checks simples baseados em taxa de erro.
    """

    def __init__(self, interval_s: float = 10.0) -> None:
        self.interval_s = interval_s
        self.start_time = time.time()
        self._layers: Dict[str, LayerMetrics] = {}
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # Registro de camadas
    # ------------------------------------------------------------------

    def register_layer(self, name: str) -> LayerMetrics:
        """Registra uma camada para monitoramento."""
        if name not in self._layers:
            self._layers[name] = LayerMetrics(name=name)
        return self._layers[name]

    def record_layer_overhead(
        self, layer: str, overhead_ms: float, error: bool = False,
    ) -> None:
        """Registra o overhead (ms) de processamento de uma camada."""
        lm = self.register_layer(layer)
        lm.message_count += 1
        lm.total_time_ms += overhead_ms
        lm.overhead_samples_ms.append(overhead_ms)
        if error:
            lm.error_count += 1

    # ------------------------------------------------------------------
    # Contadores e gauges genéricos
    # ------------------------------------------------------------------

    def increment(self, name: str, amount: int = 1) -> None:
        """Incrementa um contador nomeado."""
        self._counters[name] += amount

    def set_gauge(self, name: str, value: float) -> None:
        """Define o valor de um gauge."""
        self._gauges[name] = value

    def counter(self, name: str) -> int:
        return self._counters.get(name, 0)

    def gauge(self, name: str) -> float:
        return self._gauges.get(name, 0.0)

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self, error_threshold: float = 0.5) -> Dict[str, str]:
        """Retorna o status de saúde por camada.

        Uma camada é considerada ``unhealthy`` se a taxa de erro exceder
        ``error_threshold``.
        """
        status: Dict[str, str] = {}
        for name, lm in self._layers.items():
            if lm.message_count == 0:
                status[name] = "idle"
            else:
                error_rate = lm.error_count / lm.message_count
                status[name] = "healthy" if error_rate <= error_threshold else "unhealthy"
        return status

    # ------------------------------------------------------------------
    # Resumo
    # ------------------------------------------------------------------

    def layer_overheads(self) -> Dict[str, float]:
        """Retorna o overhead médio (ms) por camada."""
        return {name: lm.mean_overhead_ms for name, lm in self._layers.items()}

    def snapshot(self) -> Dict[str, object]:
        """Retorna um snapshot completo das métricas."""
        return {
            "uptime_s": round(time.time() - self.start_time, 2),
            "layers": {
                name: {
                    "messages": lm.message_count,
                    "errors": lm.error_count,
                    "mean_overhead_ms": round(lm.mean_overhead_ms, 4),
                    "total_time_ms": round(lm.total_time_ms, 2),
                }
                for name, lm in self._layers.items()
            },
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "health": self.health_check(),
        }

    def reset(self) -> None:
        """Reinicia todas as métricas (útil entre iterações Monte Carlo)."""
        self._layers.clear()
        self._counters.clear()
        self._gauges.clear()
        self.start_time = time.time()
