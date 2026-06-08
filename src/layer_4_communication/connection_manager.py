"""Connection Manager — Camada 4 (Comunicação) do IIAE-BR.

Gerencia conexões lógicas entre agentes e o barramento de mensagens.
Versão simplificada que controla um pool de conexões, com limite
máximo configurável, e mantém estatísticas de uso.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class Connection:
    """Representa uma conexão lógica de um agente."""

    agent_id: str
    opened_at: float = field(default_factory=time.time)
    active: bool = True
    messages_sent: int = 0
    messages_received: int = 0


class ConnectionManager:
    """Gerenciador de conexões lógicas.

    Controla um pool de conexões com limite máximo. Conexões podem ser
    abertas, fechadas e consultadas. Útil para simular limites de
    concorrência na camada de comunicação.
    """

    def __init__(self, max_connections: int = 100) -> None:
        self.max_connections = max_connections
        self._connections: Dict[str, Connection] = {}
        self.rejected_connections = 0

    def open(self, agent_id: str) -> Optional[Connection]:
        """Abre uma conexão para *agent_id*.

        Returns:
            A :class:`Connection` aberta, ou ``None`` se o limite foi
            atingido.
        """
        if agent_id in self._connections and self._connections[agent_id].active:
            return self._connections[agent_id]

        if self.active_count >= self.max_connections:
            self.rejected_connections += 1
            return None

        conn = Connection(agent_id=agent_id)
        self._connections[agent_id] = conn
        return conn

    def close(self, agent_id: str) -> None:
        """Fecha a conexão de um agente."""
        conn = self._connections.get(agent_id)
        if conn:
            conn.active = False

    def is_connected(self, agent_id: str) -> bool:
        conn = self._connections.get(agent_id)
        return bool(conn and conn.active)

    def record_send(self, agent_id: str) -> None:
        conn = self._connections.get(agent_id)
        if conn:
            conn.messages_sent += 1

    def record_receive(self, agent_id: str) -> None:
        conn = self._connections.get(agent_id)
        if conn:
            conn.messages_received += 1

    @property
    def active_count(self) -> int:
        return sum(1 for c in self._connections.values() if c.active)

    def summary(self) -> Dict[str, int]:
        return {
            "max_connections": self.max_connections,
            "active": self.active_count,
            "total": len(self._connections),
            "rejected": self.rejected_connections,
        }
