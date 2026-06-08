"""Schema.org Manager — Camada 3 (Interoperabilidade) / Semantic Mediator.

Gerencia o vocabulário **Schema.org** usado pela camada de aplicação
(agentes de venda). Constrói e valida grafos RDF de entidades Schema.org
relevantes ao e-commerce:

* ``schema:Product`` / ``schema:Offer``
* ``schema:Order`` / ``schema:OrderItem``
* ``schema:PaymentChargeSpecification``
* ``schema:Person`` / ``schema:Organization``

Utiliza ``rdflib`` para representação RDF, permitindo serialização em
JSON-LD e validação estrutural das entidades.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable

from rdflib import Graph, Literal, Namespace, RDF, URIRef
from rdflib.namespace import XSD

from src.layer_5_infrastructure.logging_service import get_logger

logger = get_logger(__name__)

SCHEMA = Namespace("http://schema.org/")
IIAE = Namespace("http://iiae-br.org/resource/")

# Tipos Schema.org suportados pela IIAE-BR
SUPPORTED_TYPES = {
    "Product",
    "Offer",
    "Order",
    "OrderItem",
    "PaymentChargeSpecification",
    "Person",
    "Organization",
}

# Propriedades esperadas (mínimas) por tipo — usado na validação
TYPE_PROPERTIES: Dict[str, set] = {
    "Product": {"name", "sku", "category", "description"},
    "Offer": {"price", "priceCurrency", "availability"},
    "Order": {"orderNumber", "orderStatus", "orderDate"},
    "OrderItem": {"orderQuantity", "orderedItem"},
    "PaymentChargeSpecification": {"price", "priceCurrency"},
    "Person": {"name"},
    "Organization": {"name", "legalName"},
}


class SchemaOrgManager:
    """Construtor/validador de entidades Schema.org em RDF."""

    namespace = SCHEMA

    def build_graph(self, entity: Dict[str, Any]) -> Graph:
        """Constrói um grafo RDF a partir de um dicionário Schema.org.

        ``entity`` deve conter ``@type`` (ou ``type``) e propriedades.
        """
        g = Graph()
        g.bind("schema", SCHEMA)
        etype = entity.get("@type") or entity.get("type", "Thing")
        subject = URIRef(IIAE[entity.get("@id", f"entity/{id(entity)}")])
        g.add((subject, RDF.type, SCHEMA[etype]))
        for key, value in entity.items():
            if key in ("@type", "type", "@id"):
                continue
            g.add((subject, SCHEMA[key], self._to_literal(value)))
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
        return etype in SUPPORTED_TYPES

    def validate(self, entity: Dict[str, Any]) -> bool:
        """Valida se a entidade possui tipo suportado e ao menos uma
        propriedade esperada para aquele tipo."""
        etype = entity.get("@type") or entity.get("type")
        if etype not in SUPPORTED_TYPES:
            logger.debug("Tipo Schema.org não suportado: %s", etype)
            return False
        expected = TYPE_PROPERTIES.get(etype, set())
        if not expected:
            return True
        present = set(entity.keys()) & expected
        return len(present) > 0

    def to_jsonld(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """Anexa o contexto Schema.org a uma entidade (forma JSON-LD)."""
        doc = {"@context": "http://schema.org/"}
        doc.update(entity)
        return doc

    def supported_types(self) -> Iterable[str]:
        return sorted(SUPPORTED_TYPES)
