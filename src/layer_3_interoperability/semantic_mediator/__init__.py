"""Semantic Mediator — Camada 3 (Interoperabilidade) do IIAE-BR.

Mediação semântica entre os vocabulários Schema.org e GoodRelations:
gerenciadores de vocabulário, mapeador de ontologias (tradução
bidirecional com cache e medição de overhead) e o mediador principal.
"""

from src.layer_3_interoperability.semantic_mediator.goodrelations_manager import (
    GoodRelationsManager,
)
from src.layer_3_interoperability.semantic_mediator.mediator import (
    SemanticMediator,
    VOCAB_GR,
    VOCAB_SCHEMA,
)
from src.layer_3_interoperability.semantic_mediator.ontology_mapper import (
    GR_TO_SCHEMA,
    OntologyMapper,
    SCHEMA_TO_GR,
    TranslationStats,
)
from src.layer_3_interoperability.semantic_mediator.schema_org_manager import (
    SchemaOrgManager,
)

__all__ = [
    "GoodRelationsManager",
    "SemanticMediator",
    "VOCAB_GR",
    "VOCAB_SCHEMA",
    "OntologyMapper",
    "TranslationStats",
    "SCHEMA_TO_GR",
    "GR_TO_SCHEMA",
    "SchemaOrgManager",
]
