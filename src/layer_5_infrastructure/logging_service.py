"""Logging Service — Camada 5 (Infraestrutura) do IIAE-BR.

Fornece um logger centralizado com níveis configuráveis (DEBUG, INFO,
WARNING, ERROR), saída para console e arquivo, e rotação de logs.

Este serviço é a base de observabilidade da arquitetura: todas as
demais camadas registram eventos através dele.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path
from typing import List, Optional

_CONFIGURED = False


def configure_logging(
    level: str = "INFO",
    outputs: Optional[List[str]] = None,
    log_file: str | Path = "results/iiae_br.log",
    max_bytes: int = 5_000_000,
    backup_count: int = 3,
    fmt: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
) -> None:
    """Configura o logging centralizado da aplicação.

    Args:
        level: Nível mínimo de log (DEBUG, INFO, WARNING, ERROR).
        outputs: Lista de saídas desejadas: ``console`` e/ou ``file``.
        log_file: Caminho do arquivo de log (quando ``file`` está em outputs).
        max_bytes: Tamanho máximo do arquivo antes da rotação.
        backup_count: Número de arquivos de backup mantidos.
        fmt: Formato das mensagens de log.
    """
    global _CONFIGURED
    outputs = outputs or ["console"]

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove handlers pré-existentes para reconfiguração idempotente
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(fmt, datefmt="%H:%M:%S")

    if "console" in outputs:
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        root.addHandler(ch)

    if "file" in outputs:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=max_bytes, backupCount=backup_count,
            encoding="utf-8",
        )
        fh.setFormatter(formatter)
        root.addHandler(fh)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Retorna um logger nomeado para uso em qualquer camada.

    Args:
        name: Nome do logger (geralmente ``__name__`` ou nome da camada).

    Returns:
        Instância de :class:`logging.Logger`.
    """
    if not _CONFIGURED:
        configure_logging()
    return logging.getLogger(name)


class LoggingService:
    """Wrapper orientado a objeto para o serviço de logging."""

    def __init__(
        self,
        level: str = "INFO",
        outputs: Optional[List[str]] = None,
        log_file: str | Path = "results/iiae_br.log",
    ) -> None:
        configure_logging(level=level, outputs=outputs, log_file=log_file)
        self._logger = get_logger("iiae-br.infra")

    def get_logger(self, name: str) -> logging.Logger:
        return get_logger(name)

    def debug(self, msg: str, *args) -> None:
        self._logger.debug(msg, *args)

    def info(self, msg: str, *args) -> None:
        self._logger.info(msg, *args)

    def warning(self, msg: str, *args) -> None:
        self._logger.warning(msg, *args)

    def error(self, msg: str, *args) -> None:
        self._logger.error(msg, *args)
