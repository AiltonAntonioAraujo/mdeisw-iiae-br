"""Camada 5 — Infraestrutura do IIAE-BR.

Serviços transversais: logging, configuração, monitoramento e segurança.
"""

from src.layer_5_infrastructure.config_service import ConfigService
from src.layer_5_infrastructure.logging_service import (
    LoggingService,
    configure_logging,
    get_logger,
)
from src.layer_5_infrastructure.monitoring_service import (
    LayerMetrics,
    MonitoringService,
)
from src.layer_5_infrastructure.security_gateway import (
    SecurityEvent,
    SecurityGateway,
)

__all__ = [
    "ConfigService",
    "LoggingService",
    "configure_logging",
    "get_logger",
    "LayerMetrics",
    "MonitoringService",
    "SecurityEvent",
    "SecurityGateway",
]
