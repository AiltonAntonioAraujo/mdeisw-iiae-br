"""Performative Mapper — Camada 3 (Interoperabilidade) / Protocol Adapter.

Mapeia as **performativas FIPA-ACL** para categorias semânticas internas
da arquitetura IIAE-BR (atos comunicativos) e define quais performativas
são respostas válidas para cada performativa de entrada. Esse mapeamento
é usado pelas máquinas de estado dos protocolos de interação para validar
a coerência das conversas entre agentes.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, Set

from src.utils.fipa_acl import Performative


class CommunicativeAct(str, Enum):
    """Categorias semânticas (atos comunicativos) FIPA."""

    ASSERTIVE = "assertive"      # informar um estado de coisas (inform, confirm)
    DIRECTIVE = "directive"      # solicitar ação (request, cfp, query)
    COMMISSIVE = "commissive"    # comprometer-se (agree, propose, accept)
    EXPRESSIVE = "expressive"    # expressar atitude (refuse, reject, failure)
    DECLARATIVE = "declarative"  # alterar estado da conversa (subscribe, cancel)


# Performativa -> ato comunicativo
_ACT_MAP: Dict[Performative, CommunicativeAct] = {
    Performative.INFORM: CommunicativeAct.ASSERTIVE,
    Performative.CONFIRM: CommunicativeAct.ASSERTIVE,
    Performative.REQUEST: CommunicativeAct.DIRECTIVE,
    Performative.CFP: CommunicativeAct.DIRECTIVE,
    Performative.QUERY_IF: CommunicativeAct.DIRECTIVE,
    Performative.QUERY_REF: CommunicativeAct.DIRECTIVE,
    Performative.AGREE: CommunicativeAct.COMMISSIVE,
    Performative.PROPOSE: CommunicativeAct.COMMISSIVE,
    Performative.ACCEPT_PROPOSAL: CommunicativeAct.COMMISSIVE,
    Performative.REFUSE: CommunicativeAct.EXPRESSIVE,
    Performative.REJECT_PROPOSAL: CommunicativeAct.EXPRESSIVE,
    Performative.FAILURE: CommunicativeAct.EXPRESSIVE,
    Performative.NOT_UNDERSTOOD: CommunicativeAct.EXPRESSIVE,
    Performative.SUBSCRIBE: CommunicativeAct.DECLARATIVE,
    Performative.CANCEL: CommunicativeAct.DECLARATIVE,
}

# Respostas válidas para cada performativa (coerência conversacional)
_VALID_REPLIES: Dict[Performative, Set[Performative]] = {
    Performative.REQUEST: {
        Performative.AGREE,
        Performative.REFUSE,
        Performative.NOT_UNDERSTOOD,
    },
    Performative.AGREE: {
        Performative.INFORM,
        Performative.FAILURE,
    },
    Performative.CFP: {
        Performative.PROPOSE,
        Performative.REFUSE,
        Performative.NOT_UNDERSTOOD,
    },
    Performative.PROPOSE: {
        Performative.ACCEPT_PROPOSAL,
        Performative.REJECT_PROPOSAL,
    },
    Performative.ACCEPT_PROPOSAL: {
        Performative.INFORM,
        Performative.FAILURE,
    },
    Performative.QUERY_IF: {
        Performative.INFORM,
        Performative.REFUSE,
        Performative.FAILURE,
    },
    Performative.QUERY_REF: {
        Performative.INFORM,
        Performative.REFUSE,
        Performative.FAILURE,
    },
    Performative.SUBSCRIBE: {
        Performative.AGREE,
        Performative.INFORM,
        Performative.REFUSE,
    },
}


class PerformativeMapper:
    """Mapeia performativas FIPA-ACL e valida respostas conversacionais."""

    def act_of(self, performative: Performative) -> CommunicativeAct:
        """Retorna o ato comunicativo de uma performativa."""
        return _ACT_MAP.get(performative, CommunicativeAct.ASSERTIVE)

    def valid_replies(self, performative: Performative) -> Set[Performative]:
        """Retorna o conjunto de respostas válidas para a performativa."""
        return _VALID_REPLIES.get(performative, set())

    def is_valid_reply(
        self, original: Performative, reply: Performative
    ) -> bool:
        """Verifica se ``reply`` é resposta coerente para ``original``."""
        return reply in self.valid_replies(original)

    def initiates_protocol(self, performative: Performative) -> bool:
        """Indica se a performativa inicia um protocolo de interação."""
        return performative in (
            Performative.REQUEST,
            Performative.CFP,
            Performative.QUERY_IF,
            Performative.QUERY_REF,
            Performative.SUBSCRIBE,
        )
