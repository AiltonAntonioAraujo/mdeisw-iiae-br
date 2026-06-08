"""Ontology Mapper — Camada 3 (Interoperabilidade) / Semantic Mediator.

Núcleo da **mediação semântica** do IIAE-BR. Realiza a tradução
**bidirecional** entre os vocabulários **Schema.org** e **GoodRelations**,
cobrindo as entidades centrais do e-commerce:

==========================  ==========================
Schema.org                  GoodRelations
==========================  ==========================
Product                     ProductOrService
Offer                       Offering
Order                       Order
OrderItem                   OrderItem
PaymentChargeSpecification  UnitPriceSpecification
Person / Organization       BusinessEntity
==========================  ==========================

Características principais:

* **Cache semântico configurável** (LRU) — a taxa de acerto (*hit rate*)
  pode ser definida explicitamente (0%, 50%, 60%, 80%, 95%) para os
  experimentos de simulação, ou operar de forma realista por chave.
* **Medição de overhead de tradução** — cada tradução tem seu tempo
  medido; acertos de cache têm custo desprezível, enquanto traduções
  efetivas (*cache miss*) incorrem no custo de mapeamento de termos.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from src.layer_5_infrastructure.logging_service import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Tabela de mapeamento Schema.org -> GoodRelations (termos e tipos)
# ---------------------------------------------------------------------------
SCHEMA_TO_GR: Dict[str, str] = {
    # Tipos
    "Product": "ProductOrService",
    "Offer": "Offering",
    "Order": "Order",
    "OrderItem": "OrderItem",
    "PaymentChargeSpecification": "UnitPriceSpecification",
    "Person": "BusinessEntity",
    "Organization": "BusinessEntity",
    # Propriedades de produto
    "name": "name",
    "description": "description",
    "sku": "hasStockKeepingUnit",
    "productID": "hasStockKeepingUnit",
    "gtin13": "hasEAN_UCC-13",
    "category": "category",
    "weight": "weight",
    "height": "height",
    "width": "width",
    "depth": "depth",
    # Oferta / preço
    "price": "hasCurrencyValue",
    "priceCurrency": "hasCurrency",
    "availability": "hasInventoryLevel",
    "seller": "hasBusinessFunction",
    "itemCondition": "condition",
    # Pedido
    "orderNumber": "hasEAN_UCC-13",
    "orderStatus": "hasBusinessFunction",
    "orderDate": "validFrom",
    "orderQuantity": "hasInventoryLevel",
    "orderedItem": "includes",
    # Pessoa / organização
    "legalName": "legalName",
    # Entrega
    "deliveryMethod": "availableDeliveryMethod",
    "shippingCost": "hasCurrencyValue",
}

# Mapeamento inverso GoodRelations -> Schema.org (gerado dinamicamente,
# preservando a primeira ocorrência para evitar ambiguidade)
GR_TO_SCHEMA: Dict[str, str] = {}
for _s, _g in SCHEMA_TO_GR.items():
    GR_TO_SCHEMA.setdefault(_g, _s)
# Ajustes explícitos para tipos com mapeamento mais natural no sentido inverso
GR_TO_SCHEMA.update({
    "ProductOrService": "Product",
    "Offering": "Offer",
    "Order": "Order",
    "OrderItem": "OrderItem",
    "UnitPriceSpecification": "PaymentChargeSpecification",
    "BusinessEntity": "Organization",
})

# Custo simulado de tradução efetiva (cache miss), em milissegundos.
# Calibrado para refletir o mapeamento de termos + (re)construção do
# documento traduzido. Acertos de cache são ~50x mais baratos.
DEFAULT_MISS_COST_MS = 1.8
DEFAULT_HIT_COST_MS = 0.03


@dataclass
class TranslationStats:
    """Estatísticas acumuladas de tradução do mediador."""

    translations: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    total_overhead_ms: float = 0.0
    overhead_samples: list = field(default_factory=list)

    @property
    def hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total else 0.0

    @property
    def avg_overhead_ms(self) -> float:
        return (
            self.total_overhead_ms / self.translations
            if self.translations else 0.0
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "translations": self.translations,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate": round(self.hit_rate, 4),
            "total_overhead_ms": round(self.total_overhead_ms, 4),
            "avg_overhead_ms": round(self.avg_overhead_ms, 6),
        }


class OntologyMapper:
    """Tradutor bidirecional Schema.org <-> GoodRelations com cache.

    Parameters
    ----------
    cache_size:
        Tamanho máximo do cache LRU.
    forced_hit_rate:
        Se definido (0.0–1.0), o mediador opera em **modo experimento**:
        a decisão de acerto/erro de cache é determinística por proporção,
        permitindo reproduzir os cenários de cache (0%, 50%, 60%, 80%, 95%).
        Se ``None``, o cache opera de forma realista (por chave de conteúdo).
    miss_cost_ms / hit_cost_ms:
        Custos simulados de tradução para *miss* e *hit*.
    """

    def __init__(
        self,
        cache_size: int = 2048,
        forced_hit_rate: Optional[float] = None,
        miss_cost_ms: float = DEFAULT_MISS_COST_MS,
        hit_cost_ms: float = DEFAULT_HIT_COST_MS,
    ) -> None:
        self.cache_size = cache_size
        self.forced_hit_rate = forced_hit_rate
        self.miss_cost_ms = miss_cost_ms
        self.hit_cost_ms = hit_cost_ms
        self._cache: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self.stats = TranslationStats()
        self._forced_counter = 0

    # ------------------------------------------------------------------
    def schema_to_goodrelations(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """Traduz uma entidade Schema.org para GoodRelations."""
        return self._translate(entity, SCHEMA_TO_GR, direction="s2g")

    def goodrelations_to_schema(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """Traduz uma entidade GoodRelations para Schema.org."""
        return self._translate(entity, GR_TO_SCHEMA, direction="g2s")

    # ------------------------------------------------------------------
    def _translate(
        self, entity: Dict[str, Any], term_map: Dict[str, str], direction: str
    ) -> Dict[str, Any]:
        start = time.perf_counter()
        key = self._cache_key(entity, direction)

        hit = self._decide_hit(key)
        if hit and key in self._cache:
            self._cache.move_to_end(key)
            result = self._cache[key]
            self._record(start, hit=True)
            return dict(result)

        # Cache miss -> tradução efetiva
        result = self._do_mapping(entity, term_map)
        self._store(key, result)
        self._record(start, hit=False)
        return result

    def _do_mapping(
        self, entity: Dict[str, Any], term_map: Dict[str, str]
    ) -> Dict[str, Any]:
        """Realiza o mapeamento termo-a-termo entre vocabulários."""
        out: Dict[str, Any] = {}
        etype = entity.get("@type") or entity.get("type")
        if etype is not None:
            etype = str(etype).split(":")[-1]
            out["@type"] = term_map.get(etype, etype)
        for key, value in entity.items():
            if key in ("@type", "type"):
                continue
            if key == "@id":
                out["@id"] = value
                continue
            mapped_key = term_map.get(key.split(":")[-1], key)
            out[mapped_key] = value
        return out

    # ------------------------------------------------------------------
    def _decide_hit(self, key: str) -> bool:
        """Decide se a tradução é um acerto de cache.

        Em **modo experimento** (``forced_hit_rate`` definido), usa uma
        sequência determinística para garantir a proporção exata. Caso
        contrário, é um acerto real apenas se a chave já estiver em cache.
        """
        if self.forced_hit_rate is None:
            return key in self._cache
        # Modo experimento: distribui acertos de forma determinística
        self._forced_counter += 1
        # número esperado de hits até agora
        expected_hits = self.forced_hit_rate * self._forced_counter
        produced = self.stats.cache_hits
        # garante que só conta como hit se houver algo em cache
        return produced < expected_hits and len(self._cache) > 0

    def _store(self, key: str, value: Dict[str, Any]) -> None:
        self._cache[key] = value
        self._cache.move_to_end(key)
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)

    def _record(self, start: float, hit: bool) -> None:
        # custo simulado + custo real de processamento medido
        simulated = self.hit_cost_ms if hit else self.miss_cost_ms
        elapsed_ms = (time.perf_counter() - start) * 1000.0 + simulated
        self.stats.translations += 1
        if hit:
            self.stats.cache_hits += 1
        else:
            self.stats.cache_misses += 1
        self.stats.total_overhead_ms += elapsed_ms
        # mantém amostras limitadas para análise estatística
        if len(self.stats.overhead_samples) < 5000:
            self.stats.overhead_samples.append(elapsed_ms)

    @staticmethod
    def _cache_key(entity: Dict[str, Any], direction: str) -> str:
        etype = entity.get("@type") or entity.get("type", "")
        keys = ",".join(sorted(k for k in entity.keys() if not k.startswith("@")))
        return f"{direction}:{etype}:{keys}"

    # ------------------------------------------------------------------
    def reset_stats(self) -> None:
        self.stats = TranslationStats()
        self._forced_counter = 0

    def clear_cache(self) -> None:
        self._cache.clear()

    def summary(self) -> Dict[str, Any]:
        return self.stats.as_dict()
