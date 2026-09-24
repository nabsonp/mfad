# Arquitetura do damfe

Três módulos em sequência. A reconstrução lê o código e produz um modelo
neutro de tecnologia; a detecção avalia esse modelo; a visualização o
apresenta. Nenhum módulo conhece o outro — todos dependem apenas do
modelo.

| | |
|---|---|
| **Motor** | tree-sitter |
| **Dependências** | 5, todas locais |
| **LLM em tempo de análise** | nenhum |
| **Determinístico** | sim |

```
código-fonte · package.json · communication.yml
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│ MÓDULO 1 — Reconstrução arquitetural                      │
│   tree-sitter + um reconstrutor por tecnologia            │
└───────────────────────────────────────────────────────────┘
        │  modelo neutro — a detecção não lê código
        ▼
┌───────────────────────────────────────────────────────────┐
│ MÓDULO 2 — Detecção de anti-padrões                       │
│   regras determinísticas sobre os artefatos               │
└───────────────────────────────────────────────────────────┘
        │  artefatos + detecções
        ▼
┌───────────────────────────────────────────────────────────┐
│ MÓDULO 3 — Visualização                                   │
│   relatório HTML autocontido                              │
└───────────────────────────────────────────────────────────┘
```

---

## Módulo 1 — Reconstrução arquitetural

> Extrai do código o que descreve a arquitetura.

### Entrada

| | |
|---|---|
| código-fonte | `.js` · `.jsx` · `.ts` · `.tsx` |
| `package.json` | nomes e dependências dos pacotes |
| `.damfe/communication.yml` | opcional — mecanismo próprio de mensagem |
| `.damfe/domains.yml` | opcional — domínios de negócio declarados |

### Mecanismo

**tree-sitter** — árvore sintática, sem executar o código e sem rede.

**Reconstrutores, um por tecnologia:**

| tecnologia | estado |
|---|---|
| single-spa | implementado |
| Bit | planejado |
| qiankun | planejado |
| a sua implementação | soquete livre |

Cada reconstrutor implementa a mesma porta e se registra. Trocar de
tecnologia não toca nos módulos 2 e 3.

Para uma tecnologia nova, um prompt assistido por LLM conduz a escrita do
reconstrutor — o código sai revisado e versionado, e a análise segue
determinística. O prompt está em [skills/](skills/).

### Artefatos extraídos

| artefato | campos |
|---|---|
| `MicroFrontend` | id, rotas, papel, LOC, arquivos |
| `Screen` | componente, rota resolvida |
| `Fragment` | nome, arquivo de definição |
| `FragmentImport` | consumidor → provedor, fragmento, props |
| `Navigation` | origem → destino, URL resolvida, confiança |
| `Communication` | origem → destino, canal, mecanismo |
| `ApiCall` | método, caminho, telas que alcançam |
| `StateAccess` | fatia de estado lida, biblioteca |
| `Domain` | nome, rotas, endpoints, subdomínios, membros resolvidos |

### Saída

```
artifacts/
  microfrontends.json
  fragment_imports.json
  navigations.json
  communications.json
  api_calls.json
  state_accesses.json
  domains.json
```

Todas gravadas a cada execução, inclusive vazias — senão o arquivo da
execução anterior permaneceria e a etapa seguinte leria dado defasado.

Uma coleção por arquivo, versionável: o diff entre dois commits mostra
que acoplamento surgiu ou sumiu.

---

## Módulo 2 — Detecção de anti-padrões

> Avalia os artefatos — agnóstico à tecnologia de origem.

### Entrada

`artifacts/*.json` — o modelo neutro do módulo 1.

Uma regra recebe o `ArtifactSet` e não sabe se veio de single-spa, Bit ou
qiankun. É isso que a torna reutilizável.

### Regras

#### `cyclic-dependency`
Micro frontends que dependem uns dos outros em ciclo.

| | |
|---|---|
| **Entrada** | `FragmentImport` · `Navigation` · `Communication` |
| **Saída** | Uma ocorrência por ciclo, com a cadeia ordenada e a relação que o produziu. |

#### `hub-like-dependency`
Tela que agrega fragmentos de vários micro frontends.

| | |
|---|---|
| **Entrada** | `Screen` · `FragmentImport.renders` |
| **Saída** | Uma ocorrência por tela, com os provedores distintos e os fragmentos. |

#### `one-for-all`
Micro frontend ligado a quase todos os demais.

| | |
|---|---|
| **Entrada** | `FragmentImport` · `Navigation` · `Communication` |
| **Saída** | Uma ocorrência por micro frontend, com a cobertura e a separação entre entrada e saída. |

#### `hammering-apis`
Rota de serviço consumida por mais de um micro frontend.

| | |
|---|---|
| **Entrada** | `ApiCall` |
| **Saída** | Uma ocorrência por rota compartilhada, com métodos e consumidores. |

#### `global-state-communication`
Estado global lido por mais de um micro frontend.

| | |
|---|---|
| **Entrada** | `StateAccess` |
| **Saída** | Ocorrência única e binária, com as fatias compartilhadas e quem lê cada uma. |

#### `mega-frontend`
Micro frontend que serve mais de um domínio de negócio.

| | |
|---|---|
| **Entrada** | `Domain` e `Screen` — ou `MicroFrontend.size` sem mapa |
| **Saída** | Uma ocorrência por micro frontend, nomeando quais telas destoam e a que domínio pertencem. |

#### `nano-frontend`
Micro frontend que cobre parte de um domínio servido por outro.

| | |
|---|---|
| **Entrada** | `Domain` e `Screen` — ou `MicroFrontend.size` sem mapa |
| **Saída** | Uma ocorrência por micro frontend, nomeando qual o absorveria e em que proporção. |

#### `access-to-different-domains`
Micro frontend que consome serviços de vários domínios.

| | |
|---|---|
| **Entrada** | `Domain` e `ApiCall` |
| **Saída** | Uma ocorrência por micro frontend, com os domínios consumidos e os endpoints de cada um. |

**8 de 27** regras implementadas do catálogo de anti-padrões de micro
frontends. Regra nova é uma classe e uma linha de registro — mesmo
soquete dos reconstrutores. A triagem das 27 está em
[CATALOGO.md](CATALOGO.md).

### Saída

`detections.json` — regra, dimensão, mensagem, envolvidos, arquivo e
linha.

Sem escala de severidade: atribuí-la exigiria um critério justificado. No
lugar, cada ocorrência informa a **dimensão** — qual relação
arquitetural a produziu.

---

## Módulo 3 — Visualização

> Apresenta a arquitetura com os desvios sobrepostos.

### Entrada

`artifacts/*.json` e `detections.json`.

### Componentes do relatório

**1. Grafo de dependências.** Nós são micro frontends; arestas, as
relações. Cinco perspectivas alternáveis — todas, composição, navegação,
comunicação, backend compartilhado. Zoom, deslocamento e busca. O que
aparece em alguma detecção fica destacado.

**2. Relatório de anti-padrões.** Um cartão por ocorrência, em ordem
fixa: o que → onde → evidência → por que foi detectado → arquivo e
linha. *Ver no grafo* isola a evidência e atenua o resto.

**3. Tabela de micro frontends.** Telas, fragmentos, entradas, saídas,
linhas de código e anti-padrões por unidade. Clicar seleciona no grafo —
localizar visualmente deixa de funcionar acima de algumas dezenas de nós.

**4. Detalhe de cada micro frontend.** Painel com rotas próprias, telas e
suas rotas resolvidas, fragmentos expostos, serviços chamados, estado
global lido, e as dependências com direção e tipo.

**5. Serviços externos.** Endpoints ordenados por número de consumidores
— os compartilhados primeiro, porque são acoplamento via backend,
invisível nos outros grafos.

O desenho é gerado na ferramenta, não no navegador: os mesmos artefatos
produzem sempre a mesma imagem. O único script da página filtra
relações — sem ele o relatório continua correto.

### Saída

| | |
|---|---|
| `architecture.html` | arquivo único, sem CDN, abre offline |
| `features.md` | sumarização para definição de domínios |

Renderizador novo é uma classe e uma linha de registro — Mermaid, DOT ou
GraphML entram pelo mesmo soquete.

---

## O mecanismo comum

Os três soquetes — **reconstrutor**, **regra** e **renderizador** — são a
mesma coisa: uma interface declarada e um registro. Nenhuma implementação
concreta é conhecida por outro módulo; a composição acontece num único
ponto do sistema, o `composition.py`.

```
domain/                 entidades puras, sem dependência de nada
application/
  ports/driving.py      como o mundo aciona a aplicação
  ports/driven.py       o que a aplicação precisa do mundo
  use_cases/            um caso de uso por operação
adapters/
  driving/              CLI
  driven/               single-spa, regras, renderizadores, armazenamento
composition.py          único ponto que conhece implementações concretas
```

Todas as dependências apontam para dentro.
