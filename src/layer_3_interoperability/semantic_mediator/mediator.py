"""Semantic Mediator — Camada 3 (Interoperabilidade) / Semantic Mediator.

Componente **principal** da mediação semântica. Integra:

#. :class:`SchemaOrgManager` — vocabulário Schema.org (agentes de venda);
#. :class:`GoodRelationsManager` — vocabulário GoodRelations (logística);
#. :class:`OntologyMapper` — tradução bidirecional com cache e overhead.

O mediador é acionado pela camada de interoperabilidade sempre que dois
agentes que falam vocabulários diferentes precisam trocar dados. Detecta
o vocabulário de origem, valida a entidade, executa a tradução e reporta
o overhead de tradução à camada de infraestrutura (monitoramento).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from src.layer_3_interoperability.semantic_mediator.goodrelations_manager import (
    GoodRelationsManager,
)
from src.layer_3_interoperability.semantic_mediator.ontology_mapper import (
    OntologyMapper,
)
from src.layer_3_interoperability.semantic_mediator.schema_org_manager import (
    SchemaOrgManager,
)
from src.layer_5_infrastructure.logging_service import get_logger

logger = get_logger(__name__)

VOCAB_SCHEMA = "schema.org"
VOCAB_GR = "goodrelations"


class SemanticMediator:
    """Mediador semântico Schema.org <-> GoodRelations."""

    def __init__(
        self,
        mapper: Optional[OntologyMapper] = None,
        schema_manager: Optional[SchemaOrgManager] = None,
        gr_manager: Optional[GoodRelationsManager] = None,
        cache_hit_rate: float = 0.85,
        hit_time_mean: float = 1.5,
        hit_time_std: float = 0.5,
        miss_time_mean: float = 10.0,
        miss_time_std: float = 3.0,
        translation_error_rate: float = 0.001,
    ) -> None:
        self.mapper = mapper or OntologyMapper()
        self.schema_manager = schema_manager or SchemaOrgManager()
        self.gr_manager = gr_manager or GoodRelationsManager()
        self.cache_hit_rate = cache_hit_rate
        # Parâmetros de tempo de tradução (ms), calibrados via YAML
        self.hit_time_mean = hit_time_mean
        self.hit_time_std = hit_time_std
        self.miss_time_mean = miss_time_mean
        self.miss_time_std = miss_time_std
        self.translation_error_rate = translation_error_rate
        self.translation_stats: Dict[str, int] = {
            "total": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }

    # ------------------------------------------------------------------
    def translate(
        self, entity: Dict[str, Any], target_vocab: str
    ) -> Dict[str, Any]:
        """Traduz ``entity`` para o vocabulário ``target_vocab``.

        Detecta o vocabulário de origem automaticamente; se já estiver no
        vocabulário alvo, retorna uma cópia inalterada.
        """
        source = self.detect_vocabulary(entity)
        target = self._normalize_vocab(target_vocab)

        if source == target:
            return dict(entity)

        if source == VOCAB_SCHEMA and target == VOCAB_GR:
            return self.mapper.schema_to_goodrelations(entity)
        if source == VOCAB_GR and target == VOCAB_SCHEMA:
            return self.mapper.goodrelations_to_schema(entity)

        logger.debug("Tradução não suportada: %s -> %s", source, target)
        return dict(entity)

    # ------------------------------------------------------------------
    def detect_vocabulary(self, entity: Dict[str, Any]) -> str:
        """Detecta o vocabulário de uma entidade (Schema.org x GoodRelations)."""
        etype = entity.get("@type") or entity.get("type", "")
        etype = str(etype)
        if etype.startswith("gr:"):
            return VOCAB_GR
        base = etype.split(":")[-1]
        # GoodRelations possui tipos característicos
        gr_markers = {
            "ProductOrService", "Offering", "BusinessEntity",
            "UnitPriceSpecification", "PriceSpecification", "DeliveryMethod",
        }
        if base in gr_markers:
            return VOCAB_GR
        # propriedades características de GoodRelations
        gr_props = {"hasCurrencyValue", "hasInventoryLevel", "legalName",
                    "hasStockKeepingUnit", "hasBusinessFunction"}
        if set(entity.keys()) & gr_props:
            return VOCAB_GR
        return VOCAB_SCHEMA

    @staticmethod
    def _normalize_vocab(vocab: str) -> str:
        v = vocab.lower().strip()
        if v in ("gr", "goodrelations", "good-relations"):
            return VOCAB_GR
        return VOCAB_SCHEMA

    # ------------------------------------------------------------------
    def validate(self, entity: Dict[str, Any]) -> bool:
        """Valida a entidade no vocabulário detectado."""
        if self.detect_vocabulary(entity) == VOCAB_GR:
            return self.gr_manager.validate(entity)
        return self.schema_manager.validate(entity)

    def overhead_summary(self) -> Dict[str, Any]:
        """Resumo do overhead de tradução (para monitoramento)."""
        return self.mapper.summary()

    def configure_cache(self, forced_hit_rate: Optional[float]) -> None:
        """Define a taxa de acerto de cache (modo experimento)."""
        self.mapper.forced_hit_rate = forced_hit_rate
        self.mapper.reset_stats()
        self.mapper.clear_cache()

    def set_cache_hit_rate(self, rate: float) -> None:
        """Configura a taxa de acerto do cache semântico.

        Alias simplificado de :meth:`configure_cache`, aceito pelo
        :class:`SimulationEngine`.

        Args:
            rate: Taxa de acerto de cache (0.0 a 1.0).
        """
        self.cache_hit_rate = max(0.0, min(1.0, rate))
        self.configure_cache(self.cache_hit_rate)

