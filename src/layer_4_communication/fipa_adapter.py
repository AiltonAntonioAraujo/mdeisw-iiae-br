"""FIPA Adapter — Camada 4 (Comunicação) do IIAE-BR.

Adaptador de transporte FIPA-ACL na camada de comunicação. Conecta as
mensagens FIPA-ACL ao :class:`CommunicationMessageBus`, aplicando
serialização JSON-LD no envio e deserialização no recebimento.

Diferente do *Protocol Adapter* da Camada 3 (que cuida da semântica e
das máquinas de estado dos protocolos), este adaptador trata apenas do
**transporte** das mensagens.
"""

from __future__ import annotations

from typing import List, Optional

from src.layer_4_communication.connection_manager import ConnectionManager
from src.layer_4_communication.message_bus import CommunicationMessageBus
from src.layer_4_communication.serialization import JSONLDSerializer
from src.utils.fipa_acl import ACLMessage


class FIPACommunicationAdapter:
    """Adaptador de transporte FIPA-ACL (Camada 4).

    Encapsula barramento, serializador e gerenciador de conexões para
    fornecer uma interface única de envio/recebimento de mensagens
    FIPA-ACL serializadas em JSON-LD.
    """

    def __init__(
        self,
        bus: Optional[CommunicationMessageBus] = None,
        serializer: Optional[JSONLDSerializer] = None,
        connection_manager: Optional[ConnectionManager] = None,
    ) -> None:
        self.bus = bus or CommunicationMessageBus()
        self.serializer = serializer or JSONLDSerializer()
        self.connections = connection_manager or ConnectionManager()
        self.sent_count = 0
        self.received_count = 0

    def connect(self, agent_id: str) -> bool:
        """Abre conexão e registra o agente no barramento."""
        self.bus.register(agent_id)
        conn = self.connections.open(agent_id)
        return conn is not None

    def disconnect(self, agent_id: str) -> None:
        self.connections.close(agent_id)

    def send(self, msg: ACLMessage, serialize: bool = True) -> str:
        """Envia uma mensagem FIPA-ACL.

        Args:
            msg: Mensagem a enviar.
            serialize: Se ``True``, serializa em JSON-LD (round-trip)
                       antes de entregar — útil para medir overhead real.

        Returns:
            A representação JSON-LD da mensagem enviada.
        """
        payload = ""
        if serialize:
            payload = self.serializer.serialize(msg)
            # Round-trip garante fidelidade do transporte
            msg = self.serializer.deserialize(payload)
        self.bus.send(msg)
        self.connections.record_send(msg.sender)
        self.sent_count += 1
        return payload

    def receive_all(self, agent_id: str) -> List[ACLMessage]:
        msgs = self.bus.receive_all(agent_id)
        self.connections.record_receive(agent_id)
        self.received_count += len(msgs)
        return msgs

    def summary(self) -> dict:
        return {
            "sent": self.sent_count,
            "received": self.received_count,
            "serialization": self.serializer.summary(),
            "connections": self.connections.summary(),
            "bus": self.bus.summary(),
        }
