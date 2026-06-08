"""Message Bus — Camada 4 (Comunicação) do IIAE-BR.

Barramento de mensagens com suporte a publish/subscribe e roteamento
por tipo de agente. Reaproveita a :class:`MessageBus` de baixo nível
(``src.utils.fipa_acl``) e adiciona uma camada de tópicos e assinaturas.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Callable, Dict, List, Optional

from src.utils.fipa_acl import ACLMessage, MessageBus as CoreMessageBus


class CommunicationMessageBus:
    """Barramento de comunicação com publish/subscribe.

    Encapsula o :class:`CoreMessageBus` (entrega ponto-a-ponto) e
    adiciona:

    * Tópicos para publish/subscribe (ex.: por tipo de agente).
    * Roteamento por padrão de receiver.
    * Contadores de tráfego.
    """

    def __init__(self, core_bus: Optional[CoreMessageBus] = None) -> None:
        self.core = core_bus or CoreMessageBus()
        self._subscriptions: Dict[str, List[str]] = defaultdict(list)
        self._topic_handlers: Dict[str, List[Callable[[ACLMessage], None]]] = defaultdict(list)
        self.published_count = 0
        self.delivered_count = 0

    # ------------------------------------------------------------------
    # Registro / assinaturas
    # ------------------------------------------------------------------

    def register(self, agent_id: str) -> None:
        """Registra uma caixa de mensagens para um agente."""
        self.core.register(agent_id)

    def subscribe(self, topic: str, agent_id: str) -> None:
        """Inscreve um agente em um tópico (ex.: ``seller``, ``logistics``)."""
        if agent_id not in self._subscriptions[topic]:
            self._subscriptions[topic].append(agent_id)
        self.core.register(agent_id)

    def subscribe_handler(
        self, topic: str, handler: Callable[[ACLMessage], None],
    ) -> None:
        """Inscreve um callback para mensagens de um tópico."""
        self._topic_handlers[topic].append(handler)

    # ------------------------------------------------------------------
    # Envio / publicação
    # ------------------------------------------------------------------

    def send(self, msg: ACLMessage) -> None:
        """Entrega ponto-a-ponto (delegada ao core bus)."""
        self.core.send(msg)
        self.delivered_count += 1

    def publish(self, topic: str, msg: ACLMessage) -> int:
        """Publica uma mensagem para todos os assinantes de um tópico.

        Returns:
            Número de destinatários alcançados.
        """
        self.published_count += 1
        subscribers = self._subscriptions.get(topic, [])
        for agent_id in subscribers:
            routed = ACLMessage(
                performative=msg.performative,
                sender=msg.sender,
                receiver=agent_id,
                content=msg.content,
                conversation_id=msg.conversation_id,
                protocol=msg.protocol,
                ontology=msg.ontology,
            )
            self.core.send(routed)
            self.delivered_count += 1

        for handler in self._topic_handlers.get(topic, []):
            handler(msg)

        return len(subscribers)

    # ------------------------------------------------------------------
    # Recepção
    # ------------------------------------------------------------------

    def receive(self, agent_id: str) -> Optional[ACLMessage]:
        return self.core.receive(agent_id)

    def receive_all(self, agent_id: str) -> List[ACLMessage]:
        return self.core.receive_all(agent_id)

    def pending(self, agent_id: str) -> int:
        return self.core.pending(agent_id)

    @property
    def total_messages(self) -> int:
        return self.core.total_messages

    def subscribers(self, topic: str) -> List[str]:
        return list(self._subscriptions.get(topic, []))

    def summary(self) -> Dict[str, int]:
        return {
            "published": self.published_count,
            "delivered": self.delivered_count,
            "topics": len(self._subscriptions),
            "total_core_messages": self.core.total_messages,
        }
