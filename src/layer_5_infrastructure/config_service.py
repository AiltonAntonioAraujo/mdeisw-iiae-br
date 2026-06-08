"""Config Service — Camada 5 (Infraestrutura) do IIAE-BR.

Carrega a configuração da arquitetura em camadas a partir de arquivos
YAML, expõe feature flags e configurações específicas por camada.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import yaml


class ConfigService:
    """Serviço de configuração centralizado.

    Carrega ``configs/iiae_br_config.yaml`` (ou caminho informado) e
    fornece acesso tipado às configurações de cada camada, além de
    feature flags.

    Parameters:
        config_path: Caminho do arquivo YAML. Se ``None``, usa
                     ``configs/iiae_br_config.yaml`` na raiz do projeto.
    """

    def __init__(self, config_path: str | Path | None = None) -> None:
        if config_path is None:
            project_root = Path(__file__).resolve().parents[2]
            config_path = project_root / "configs" / "iiae_br_config.yaml"
        self.config_path = Path(config_path)
        self._data: Dict[str, Any] = {}
        self.load()

    @classmethod
    def from_file(cls, config_path: str | Path) -> "ConfigService":
        """Cria um :class:`ConfigService` a partir de um caminho de arquivo.

        Conveniência para inicialização explícita
        (ex.: ``ConfigService.from_file("configs/iiae_br_config.yaml")``).
        """
        return cls(config_path)

    def load(self) -> Dict[str, Any]:
        """Carrega (ou recarrega) o arquivo de configuração."""
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as fh:
                self._data = yaml.safe_load(fh) or {}
        else:
            self._data = {}
        return self._data

    # ------------------------------------------------------------------
    # Acesso genérico
    # ------------------------------------------------------------------

    def get(self, *keys: str, default: Any = None) -> Any:
        """Acessa um valor aninhado de configuração.

        Example:
            ``cfg.get("orchestration", "max_queue_size", default=1000)``
        """
        node: Any = self._data
        for key in keys:
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                return default
        return node

    # ------------------------------------------------------------------
    # Acesso por camada
    # ------------------------------------------------------------------

    def layer_config(self, layer: str) -> Dict[str, Any]:
        """Retorna a configuração de uma camada específica."""
        return self.get(layer, default={}) or {}

    @property
    def layers(self) -> list[str]:
        """Lista de camadas habilitadas na arquitetura."""
        return self.get("architecture", "layers", default=[]) or []

    # ------------------------------------------------------------------
    # Feature flags
    # ------------------------------------------------------------------

    def is_enabled(self, *keys: str) -> bool:
        """Verifica uma feature flag booleana."""
        val = self.get(*keys, default=False)
        return bool(val)

    def feature_flag(self, name: str, default: bool = False) -> bool:
        """Retorna o valor de uma feature flag global."""
        flags = self.get("feature_flags", default={}) or {}
        return bool(flags.get(name, default))

    @property
    def raw(self) -> Dict[str, Any]:
        """Retorna o dicionário de configuração completo."""
        return dict(self._data)
