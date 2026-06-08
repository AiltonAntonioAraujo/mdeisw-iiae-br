"""Identity Manager — Camada 3 (Interoperabilidade) do IIAE-BR.

Gerencia a **identidade** dos agentes na federação IIAE-BR. Atribui
identificadores únicos (AID — *Agent Identifier* no estilo FIPA),
mantém o vocabulário declarado por cada agente (Schema.org ou
GoodRelations) e emite/valida credenciais simples usadas pelo
*Security Gateway* da camada de infraestrutura.

Versão simplificada (porém funcional): as credenciais são tokens
determinísticos derivados do AID; não há criptografia forte, adequado
ao escopo de simulação do experimento.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional

from src.layer_5_infrastructure.logging_service import get_logger

logger = get_logger(__name__)


@dataclass
class AgentIdentity:
    """Identidade de um agente na federação."""

    aid: str
    name: str
    role: str
    vocabulary: str            # 'schema.org' | 'goodrelations'
    credential: str = ""
    metadata: Dict[str, str] = field(default_factory=dict)


class IdentityManager:
    """Registro e validação de identidades de agentes."""

    def __init__(self, secret: str = "iiae-br") -> None:
        self._secret = secret
        self._identities: Dict[str, AgentIdentity] = {}

    # ------------------------------------------------------------------
    def register(
        self,
        name: str,
        role: str,
        vocabulary: str = "schema.org",
        aid: Optional[str] = None,
    ) -> AgentIdentity:
        """Registra um agente e retorna sua identidade com credencial."""
        aid = aid or f"{name}@iiae-br/{uuid.uuid4().hex[:8]}"
        credential = self._make_credential(aid)
        identity = AgentIdentity(
            aid=aid, name=name, role=role,
            vocabulary=vocabulary, credential=credential,
        )
        self._identities[aid] = identity
        logger.debug("Identidade registrada: %s (%s)", aid, role)
        return identity

    def _make_credential(self, aid: str) -> str:
        raw = f"{aid}:{self._secret}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:32]

    # ------------------------------------------------------------------
    def validate(self, aid: str, credential: str) -> bool:
        """Valida a credencial de um agente."""
        identity = self._identities.get(aid)
        if identity is None:
            return False
        return identity.credential == credential

    def get(self, aid: str) -> Optional[AgentIdentity]:
        return self._identities.get(aid)

    def vocabulary_of(self, aid: str) -> Optional[str]:
        identity = self._identities.get(aid)
        return identity.vocabulary if identity else None

    def all_aids(self) -> list:
        return list(self._identities.keys())

    def count(self) -> int:
        return len(self._identities)
