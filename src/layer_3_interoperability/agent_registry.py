"""Agent Registry — Camada 3 (Interoperabilidade) do IIAE-BR.

Diretório de agentes (estilo *FIPA Directory Facilitator*). Mantém o
registro estático dos agentes disponíveis na federação, seus papéis,
vocabulários e serviços oferecidos, suportando a **descoberta de
agentes** por papel, serviço ou vocabulário. É consultado pela camada de
orquestração para rotear mensagens ao agente adequado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.layer_5_infrastructure.logging_service import get_logger

logger = get_logger(__name__)


@dataclass
class AgentDescriptor:
    """Descrição de um agente registrado no diretório."""

    aid: str
    role: str                       # 'sales' | 'logistics' | 'buyer' | ...
    vocabulary: str                 # 'schema.org' | 'goodrelations'
    services: List[str] = field(default_factory=list)
    address: str = ""               # tópico/endereço no barramento
    active: bool = True


class AgentRegistry:
    """Registro e descoberta de agentes."""

    def __init__(self) -> None:
        self._agents: Dict[str, AgentDescriptor] = {}

    # ------------------------------------------------------------------
    def register(
        self,
        aid: str,
        role: str,
        vocabulary: str,
        services: Optional[List[str]] = None,
        address: str = "",
    ) -> AgentDescriptor:
        desc = AgentDescriptor(
            aid=aid, role=role, vocabulary=vocabulary,
            services=services or [], address=address or aid,
        )
        self._agents[aid] = desc
        logger.debug("Agente registrado no diretório: %s (%s)", aid, role)
        return desc

    def deregister(self, aid: str) -> None:
        self._agents.pop(aid, None)

    # ------------------------------------------------------------------
    def find_by_role(self, role: str) -> List[AgentDescriptor]:
        return [a for a in self._agents.values() if a.role == role and a.active]

    def find_by_service(self, service: str) -> List[AgentDescriptor]:
        return [
            a for a in self._agents.values()
            if service in a.services and a.active
        ]

    def find_by_vocabulary(self, vocabulary: str) -> List[AgentDescriptor]:
        return [
            a for a in self._agents.values()
            if a.vocabulary == vocabulary and a.active
        ]

    def get(self, aid: str) -> Optional[AgentDescriptor]:
        return self._agents.get(aid)

    def all(self) -> List[AgentDescriptor]:
        return list(self._agents.values())

    def count(self) -> int:
        return len(self._agents)
