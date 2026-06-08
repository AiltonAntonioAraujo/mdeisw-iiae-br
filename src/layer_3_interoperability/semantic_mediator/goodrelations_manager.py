"""GoodRelations Manager — Camada 3 (Interoperabilidade) / Semantic Mediator.

Gerencia o vocabulário **GoodRelations** usado pela camada de aplicação
(agentes de logística). Constrói e valida grafos RDF de entidades
GoodRelations relevantes ao e-commerce:

* ``gr:BusinessEntity``
* ``gr:ProductOrService``
* ``gr:Offering``
* ``gr:PriceSpecification`` / ``gr:UnitPriceSpecification``
* ``gr:DeliveryMethod``

Utiliza ``rdflib`` para representação RDF e validação estrutural.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable

from rdflib import Graph, Literal, Namespace, RDF, URIRef
from rdflib.namespace import XSD

from src.layer_5_infrastructure.logging_service import get_logger

logger = get_logger(__name__)

GR = Namespace("http://purl.org/goodrelations/v1#")
IIAE = Namespace("http://iiae-br.org/resource/")

# Tipos GoodRelations suportados pela IIAE-BR
SUPPORTED_TYPES = {
    "ProductOrService",
    "Offering",
    "Order",
    "OrderItem",
    "PriceSpecification",
    "UnitPriceSpecification",
    "BusinessEntity",
    "DeliveryMethod",
}

# Propriedades esperadas (mínimas) por tipo
TYPE_PROPERTIES: Dict[str, set] = {
    "ProductOrService": {"name", "hasStockKeepingUnit", "category", "description"},
    "Offering": {"hasCurrencyValue", "hasCurrency", "hasInventoryLevel"},
    "Order": {"hasEAN_UCC-13", "hasBusinessFunction", "validFrom"},
    "OrderItem": {"hasInventoryLevel", "includes"},
    "PriceSpecification": {"hasCurrencyValue", "hasCurrency"},
    "UnitPriceSpecification": {"hasCurrencyValue", "hasCurrency"},
    "BusinessEntity": {"legalName", "name"},
    "DeliveryMethod": {"availableDeliveryMethod"},
}


class GoodRelationsManager:
    """Construtor/validador de entidades GoodRelations em RDF."""

    namespace = GR

    def build_graph(self, entity: Dict[str, Any]) -> Graph:
        """Constrói um grafo RDF a partir de um dicionário GoodRelations."""
        g = Graph()
        g.bind("gr", GR)
        etype = entity.get("@type") or entity.get("type", "ProductOrService")
        # remove eventual prefixo 'gr:'
        etype = etype.split(":")[-1]
        subject = URIRef(IIAE[entity.get("@id", f"entity/{id(entity)}")])
        g.add((subject, RDF.type, GR[etype]))
        for key, value in entity.items():
            if key in ("@type", "type", "@id"):
                continue
            key = key.split(":")[-1]
            g.add((subject, GR[key], self._to_literal(value)))
        return g

    @staticmethod
    def _to_literal(value: Any) -> Literal:
        if isinstance(value, bool):
            return Literal(value, datatype=XSD.boolean)
        if isinstance(value, int):
            return Literal(value, datatype=XSD.integer)
        if isinstance(value, float):
            return Literal(value, datatype=XSD.decimal)
        return Literal(str(value))

    # ------------------------------------------------------------------
    def is_supported(self, etype: str) -> bool:
        return etype.split(":")[-1] in SUPPORTED_TYPES

    def validate(self, entity: Dict[str, Any]) -> bool:
        etype = entity.get("@type") or entity.get("type")
        if etype is None:
            return False
        etype = etype.split(":")[-1]
        if etype not in SUPPORTED_TYPES:
            logger.debug("Tipo GoodRelations não suportado: %s", etype)
            return False
        expected = TYPE_PROPERTIES.get(etype, set())
        if not expected:
            return True
        present = {k.split(":")[-1] for k in entity.keys()} & expected
        return len(present) > 0

    def to_jsonld(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """Anexa o contexto GoodRelations a uma entidade (forma JSON-LD)."""
        doc = {"@context": {"gr": "http://purl.org/goodrelations/v1#"}}
        doc.update(entity)
        return doc

    def supported_types(self) -> Iterable[str]:
        return sorted(SUPPORTED_TYPES)
