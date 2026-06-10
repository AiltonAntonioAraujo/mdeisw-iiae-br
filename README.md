# IIAE-BR — Interoperabilidade de Agentes Inteligentes no E-commerce Brasileiro

Experimento de simulação Monte Carlo para validação empírica da interoperabilidade de agentes inteligentes em plataformas de e-commerce brasileiras, utilizando o dataset público Olist (Kaggle).

O projeto implementa a **arquitetura IIAE-BR em 5 camadas**, com foco na
interoperabilidade entre os vocabulários **Schema.org** e **GoodRelations**,
usando o protocolo **FIPA-ACL** e serialização **JSON-LD**.

## Arquitetura em 5 Camadas

```
┌─────────────────────────────────────────────────────────────────────┐
│  CAMADA 1 — APLICAÇÃO                                                 │
│  Sales Agent (Schema.org)          Logistics Agent (GoodRelations)    │
│  • Product, Offer, Order           • BusinessEntity, ProductOrService │
│  • comportamentos FIPA-ACL         • UnitPriceSpecification           │
└───────────────────────────────┬───────────────────────────────────────┘
                                 │  mensagens FIPA-ACL
┌───────────────────────────────▼───────────────────────────────────────┐
│  CAMADA 2 — ORQUESTRAÇÃO                                              │
│  Orchestrator · ConversationManager · WorkflowCoordinator · LoadBalancer│
│  • roteamento inteligente · fila de prioridade · round-robin          │
└───────────────────────────────┬───────────────────────────────────────┘
                                 │
┌───────────────────────────────▼───────────────────────────────────────┐
│  CAMADA 3 — INTEROPERABILIDADE  (CENTRAL)                             │
│  ┌─ Protocol Adapter ──────────┐   ┌─ Semantic Mediator ───────────┐  │
│  │ FIPAACLAdapter              │   │ SemanticMediator              │  │
│  │ MessageParser               │   │ SchemaOrgManager              │  │
│  │ PerformativeMapper          │   │ GoodRelationsManager          │  │
│  │ InteractionProtocolEngine   │   │ OntologyMapper (cache+overhead)│  │
│  │ (Request/Query/             │   │ Schema.org ⇄ GoodRelations    │  │
│  │  Contract-Net/Subscribe)    │   └────────────────────────────────┘  │
│  └─────────────────────────────┘                                       │
│  IdentityManager · ContextManager · AgentRegistry                     │
└───────────────────────────────┬───────────────────────────────────────┘
                                 │
┌───────────────────────────────▼───────────────────────────────────────┐
│  CAMADA 4 — COMUNICAÇÃO                                               │
│  CommunicationMessageBus · JSONLDSerializer · FIPACommunicationAdapter │
│  ConnectionManager   • transporte e serialização JSON-LD              │
└───────────────────────────────┬───────────────────────────────────────┘
                                 │
┌───────────────────────────────▼───────────────────────────────────────┐
│  CAMADA 5 — INFRAESTRUTURA  (transversal)                            │
│  LoggingService · ConfigService · MonitoringService · SecurityGateway  │
└─────────────────────────────────────────────────────────────────────┘
```

> Documentação detalhada da arquitetura em [`docs/arquitetura_iiae_br.md`](docs/arquitetura_iiae_br.md).

## Casos de Uso (estudo de caso, seção 3.3)

O experimento executa **três casos de uso** que percorrem as cinco
camadas e exercitam a interoperabilidade semântica. Os fluxos completos
(diagramas de sequência FIPA-ACL) estão em
[`docs/use_cases_sequence_diagrams.md`](docs/use_cases_sequence_diagrams.md).

| Caso de uso | Descrição | Traduções semânticas |
|---|---|---|
| **UC1 — Consultar Produto e Disponibilidade** | O Agente de Vendas responde a consultas de catálogo/estoque (Schema.org). | 0 (intra-vocabulário) |
| **UC2 — Calcular Prazo e Frete** | O Agente de Vendas solicita à Logística o cálculo de prazo/frete; demonstra a tradução **Schema.org ⇄ GoodRelations**. | 2 |
| **UC3 — Processar Pedido (ponta a ponta)** | Integra UC1 + UC2: registra o pedido, calcula a entrega (com tradução semântica) e confirma o pedido. | 2 |

### Comportamentos dos Agentes (FIPA-ACL)

**SalesAgent** (Camada 1, vocabulário Schema.org):

- `consultar_produto` — responde consultas de produto (`Product`/`Offer`);
- `verificar_disponibilidade` — consulta o estoque de um produto;
- `processar_pedido` — valida e registra o pedido, gerando um `REQUEST`
  de entrega à logística;
- `atualizar_status` — atualiza o pedido a partir do `INFORM` da logística.

**LogisticsAgent** (Camada 1, vocabulário GoodRelations):

- `calcular_prazo` — estima o prazo de entrega (geolocalização Olist);
- `calcular_frete` — calcula o custo de frete (distância, peso, modalidade);
- `rastrear_entrega` — reporta o status de uma entrega em andamento;
- `notificar_status` — envia atualizações ao Agente de Vendas (`INFORM`).

A tradução entre os vocabulários é responsabilidade **exclusiva** da
Camada 3 (Mediador Semântico); os agentes não conhecem o vocabulário do par.

## Estrutura do Projeto

```
experimento_iiae_br/
├── configs/
│   └── iiae_br_config.yaml        # Configuração única (arquitetura + experimento Monte Carlo)
├── data/                          # Dataset Olist (CSVs)
├── docs/
│   ├── arquitetura_iiae_br.md     # Documentação da arquitetura em camadas
│   └── use_cases_sequence_diagrams.md  # Diagramas de sequência (UC1/UC2/UC3)
├── results/                       # CSV, JSON, charts/, relatorio_final.txt
├── src/
│   ├── layer_1_application/       # CAMADA 1 — Aplicação
│   │   ├── sales_agent.py         #   Agente de vendas (Schema.org)
│   │   └── logistics_agent.py     #   Agente de logística (GoodRelations)
│   ├── layer_2_orchestration/     # CAMADA 2 — Orquestração
│   │   ├── orchestrator.py        #   Roteamento + fila de prioridade
│   │   ├── conversation_manager.py#   Ciclo de vida das conversas
│   │   ├── workflow_coordinator.py#   Fluxos multi-agente
│   │   └── load_balancer.py       #   Balanceamento (round-robin)
│   ├── layer_3_interoperability/  # CAMADA 3 — Interoperabilidade (CENTRAL)
│   │   ├── protocol_adapter/      #   Adaptador FIPA-ACL
│   │   │   ├── fipa_acl_adapter.py
│   │   │   ├── message_parser.py
│   │   │   ├── performative_mapper.py
│   │   │   └── interaction_protocol.py  # máquinas de estado
│   │   ├── semantic_mediator/     #   Mediação semântica
│   │   │   ├── mediator.py
│   │   │   ├── schema_org_manager.py
│   │   │   ├── goodrelations_manager.py
│   │   │   └── ontology_mapper.py # tradução bidirecional + cache + overhead
│   │   ├── identity_manager.py
│   │   ├── context_manager.py
│   │   └── agent_registry.py
│   ├── layer_4_communication/     # CAMADA 4 — Comunicação
│   │   ├── message_bus.py
│   │   ├── serialization.py       #   JSON-LD
│   │   ├── fipa_adapter.py
│   │   └── connection_manager.py
│   ├── layer_5_infrastructure/    # CAMADA 5 — Infraestrutura
│   │   ├── logging_service.py
│   │   ├── config_service.py
│   │   ├── monitoring_service.py
│   │   └── security_gateway.py
│   ├── analysis/                  # Métricas, gráficos, relatórios, estatística
│   ├── simulation/
│   │   ├── engine.py              #   SimulationEngine (Monte Carlo sobre casos de uso reais)
│   │   ├── use_cases.py           #   UseCaseSimulator (UC1/UC2/UC3, 5 camadas, dados Olist)
│   │   └── layer_overhead.py      #   Medição de overhead por camada
│   └── utils/                     # data_loader (OlistDataset), fipa_acl
├── tests/                         # Testes unitários (38 testes)
├── main.py                        # Ponto de entrada
├── requirements.txt
└── pyproject.toml
```

## Tecnologias

| Componente | Biblioteca |
|---|---|
| Protocolo agentes | FIPA-ACL (implementação própria) |
| Vocabulários / RDF | rdflib (Schema.org, GoodRelations) |
| Serialização | JSON-LD |
| Dados | pandas, numpy |
| Estatística | scipy (Kruskal-Wallis, Mann-Whitney, Cohen's d) |
| Visualização | matplotlib, seaborn |

## Execução

```bash
# Instalação
pip install -r requirements.txt

# Testes unitários (47 testes)
python -m pytest -q

# Experimento completo (todos os cenários + análise de cache)
python main.py

# Execução rápida (1.000 iterações por cenário)
python main.py --iterations 1000

# Apenas a análise de sensibilidade do cache
python main.py --cache-analysis

# Sem gerar gráficos
python main.py --no-charts --verbose
```

> **Nota sobre o dataset.** O motor executa os casos de uso reais sobre os
> CSVs do Olist em `data/`. Se os arquivos não estiverem presentes, a
> simulação cai automaticamente para uma **carga sintética equivalente**,
> preservando a mesma estrutura de chamadas às cinco camadas (útil para
> testes e ambientes sem o dataset).

### Argumentos de linha de comando

| Argumento | Valores | Descrição |
|---|---|---|
| `--config` | caminho | Arquivo de configuração (padrão: `configs/iiae_br_config.yaml`) |
| `--iterations`, `-n` | inteiro | Iterações Monte Carlo por cenário (padrão: configuração) |
| `--cache-analysis` | — | Executa apenas a análise de sensibilidade do cache |
| `--no-charts` | — | Pula a geração de gráficos |
| `--verbose`, `-v` | — | Log detalhado |

## Cenários de Carga

Os cenários são lidos da configuração (`scenarios`) pelo `ScenarioManager`.
Cada iteração Monte Carlo sorteia um caso de uso conforme o `use_case_mix`
(UC1 20 %, UC2 30 %, UC3 50 %) e o executa de ponta a ponta sob o
multiplicador de carga do cenário.

| Cenário | Multiplicador | Descrição |
|---|---|---|
| Normal | 1× | Operação normal |
| Pico | 3× | Horário de pico |
| Black Friday | 10× | Evento sazonal |
| Estresse | 20× | Teste extremo |

## Análise de Cache

Avaliação de sensibilidade do **Mediador Semântico** (Camada 3) com taxas
de acerto de cache de **0 %, 50 %, 80 % e 95 %**. Para cada taxa, o motor
reexecuta o cenário-base e compara a latência fim-a-fim e o tempo de
tradução com o cache frio (0 %), quantificando a redução obtida.

```bash
python main.py --cache-analysis
```

## Métricas

O experimento coleta cinco grupos de métricas (A–E) por cenário:

- **(A) Latência fim-a-fim**: média, mediana, desvio, P50, P95, P99 (ms);
- **(B) Latência de tradução**: tempo médio de tradução semântica e taxa de
  transações que exigem tradução (UC2/UC3);
- **(C) Throughput**: médio e máximo (msg/s) e taxa de rejeição;
- **(D) Confiabilidade**: taxa de sucesso, de *timeout* e de erro de tradução;
- **(E) Cache semântico**: taxas de *hit*/*miss* observadas e o ganho de
  latência por nível de cache.

Adicionalmente, o **overhead por camada** (ms) é medido por transação; o
custo da camada de **Interoperabilidade** varia com a taxa de acerto do
cache semântico (tradução Schema.org ⇄ GoodRelations). A análise estatística
emprega **Kruskal-Wallis**, **Mann-Whitney U** e **Cohen's d**.

### SLAs avaliados

| SLA | Alvo |
|---|---|
| Latência fim-a-fim | < 150 ms |
| Throughput | > 1.000 msg/s |
| Taxa de rejeição | < 1 % |
| Taxa de sucesso | > 99,9 % |

## Saídas

- `results/reports/simulation_results.json` — Métricas (A–E) de todos os cenários
- `results/reports/cache_sensitivity.json` — Resultado da análise de cache
- `results/reports/tabela_sensibilidade_cache.csv` — Tabela de sensibilidade do cache
- `results/charts/*.png` — Gráficos de análise (rejeição, latência, throughput,
  sucesso, distribuição de latência, sensibilidade de cache)

## Licença

MIT
