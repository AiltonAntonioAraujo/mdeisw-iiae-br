"""Camada 1 — Aplicação do IIAE-BR.

Agentes de domínio do marketplace. O agente de **vendas** fala
Schema.org; o agente de **logística** fala GoodRelations. A
interoperabilidade entre eles é garantida pelas camadas inferiores.
"""

from src.layer_1_application.logistics_agent import LogisticsAgent
from src.layer_1_application.sales_agent import SalesAgent

__all__ = ["LogisticsAgent", "SalesAgent"]
