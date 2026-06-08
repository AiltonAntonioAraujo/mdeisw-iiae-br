"""Workflow Coordinator — Camada 2 (Orquestração) do IIAE-BR.

Coordena **fluxos de trabalho** multi-etapas que envolvem mais de um
agente — por exemplo, o fluxo de compra: consulta de produto (venda) →
cálculo de frete (logística) → fechamento do pedido. Define os passos,
o papel responsável por cada passo e acompanha a progressão do fluxo,
encaminhando à orquestração qual o próximo agente a ser acionado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from src.layer_5_infrastructure.logging_service import get_logger

logger = get_logger(__name__)


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class WorkflowStep:
    """Um passo de um fluxo de trabalho."""

    name: str
    role: str                  # papel responsável pelo passo
    performative: str = "request"
    status: StepStatus = StepStatus.PENDING


@dataclass
class Workflow:
    """Instância de um fluxo de trabalho em execução."""

    workflow_id: str
    name: str
    steps: List[WorkflowStep]
    current: int = 0
    data: Dict[str, object] = field(default_factory=dict)

    @property
    def finished(self) -> bool:
        return self.current >= len(self.steps)

    def current_step(self) -> Optional[WorkflowStep]:
        if self.finished:
            return None
        return self.steps[self.current]


# Definições de fluxos padrão da IIAE-BR
WORKFLOW_TEMPLATES: Dict[str, List[Dict[str, str]]] = {
    "purchase": [
        {"name": "consulta_produto", "role": "sales", "performative": "query-ref"},
        {"name": "calculo_frete", "role": "logistics", "performative": "request"},
        {"name": "fechamento_pedido", "role": "sales", "performative": "request"},
    ],
    "availability": [
        {"name": "consulta_estoque", "role": "sales", "performative": "query-if"},
    ],
    "delivery_quote": [
        {"name": "calculo_frete", "role": "logistics", "performative": "request"},
    ],
}


class WorkflowCoordinator:
    """Cria e coordena fluxos de trabalho multi-agente."""

    def __init__(self) -> None:
        self._workflows: Dict[str, Workflow] = {}
        self.completed = 0
        self.failed = 0

    # ------------------------------------------------------------------
    def start(self, workflow_id: str, template: str) -> Workflow:
        """Inicia um fluxo a partir de um template conhecido."""
        steps_def = WORKFLOW_TEMPLATES.get(template, [])
        steps = [
            WorkflowStep(s["name"], s["role"], s.get("performative", "request"))
            for s in steps_def
        ]
        wf = Workflow(workflow_id, template, steps)
        self._workflows[workflow_id] = wf
        return wf

    def advance(self, workflow_id: str, success: bool = True) -> Optional[WorkflowStep]:
        """Avança o fluxo e retorna o próximo passo (ou ``None`` se terminou)."""
        wf = self._workflows.get(workflow_id)
        if wf is None or wf.finished:
            return None
        step = wf.steps[wf.current]
        step.status = StepStatus.DONE if success else StepStatus.FAILED
        if not success:
            self.failed += 1
            wf.current = len(wf.steps)  # encerra o fluxo
            return None
        wf.current += 1
        if wf.finished:
            self.completed += 1
            return None
        return wf.current_step()

    def next_role(self, workflow_id: str) -> Optional[str]:
        wf = self._workflows.get(workflow_id)
        step = wf.current_step() if wf else None
        return step.role if step else None

    def get(self, workflow_id: str) -> Optional[Workflow]:
        return self._workflows.get(workflow_id)

    def summary(self) -> Dict[str, int]:
        return {
            "total": len(self._workflows),
            "completed": self.completed,
            "failed": self.failed,
        }
