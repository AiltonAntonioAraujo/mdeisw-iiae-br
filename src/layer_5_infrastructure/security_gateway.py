"""Security Gateway — Camada 5 (Infraestrutura) do IIAE-BR.

Versão simplificada de um gateway de segurança. Realiza validações
básicas de mensagens (autenticação de remetente conhecido, verificação
de campos obrigatórios) e mantém um log de eventos de segurança.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class SecurityEvent:
    """Evento de segurança registrado pelo gateway."""

    timestamp: float
    event_type: str          # auth_ok, auth_fail, blocked, validated
    agent_id: str
    detail: str = ""


class SecurityGateway:
    """Gateway de segurança simplificado.

    Mantém uma lista de agentes confiáveis (allowlist) e valida o acesso
    de remetentes. Em modo permissivo (padrão), apenas registra; em modo
    estrito, bloqueia remetentes desconhecidos.
    """

    def __init__(self, strict: bool = False) -> None:
        self.strict = strict
        self._trusted_agents: Set[str] = set()
        self._events: List[SecurityEvent] = []
        self.blocked_count = 0
        self.validated_count = 0

    def register_agent(self, agent_id: str) -> None:
        """Adiciona um agente à lista de confiáveis."""
        self._trusted_agents.add(agent_id)

    def register_many(self, agent_ids: List[str]) -> None:
        for aid in agent_ids:
            self.register_agent(aid)

    def authorize(self, agent_id: str) -> bool:
        """Autoriza (ou não) um agente a enviar mensagens.

        Em modo permissivo sempre autoriza, registrando o evento. Em modo
        estrito, autoriza apenas agentes confiáveis.
        """
        trusted = agent_id in self._trusted_agents
        if trusted:
            self._log("auth_ok", agent_id)
            return True

        if self.strict:
            self.blocked_count += 1
            self._log("blocked", agent_id, "agente desconhecido (modo estrito)")
            return False

        self._log("auth_fail", agent_id, "agente desconhecido (modo permissivo)")
        return True

    def validate_message(self, msg_dict: Dict[str, object]) -> bool:
        """Valida campos mínimos de segurança de uma mensagem."""
        required = ("performative", "sender", "receiver")
        ok = all(msg_dict.get(f) for f in required)
        if ok:
            self.validated_count += 1
            self._log("validated", str(msg_dict.get("sender", "?")))
        else:
            self._log("blocked", str(msg_dict.get("sender", "?")), "campos ausentes")
        return ok

    # ------------------------------------------------------------------

    def _log(self, event_type: str, agent_id: str, detail: str = "") -> None:
        self._events.append(SecurityEvent(
            timestamp=time.time(),
            event_type=event_type,
            agent_id=agent_id,
            detail=detail,
        ))

    @property
    def events(self) -> List[SecurityEvent]:
        return list(self._events)

    def summary(self) -> Dict[str, int]:
        return {
            "trusted_agents": len(self._trusted_agents),
            "blocked": self.blocked_count,
            "validated": self.validated_count,
            "total_events": len(self._events),
        }
