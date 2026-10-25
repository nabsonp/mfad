# MFAD

Análise estática de arquiteturas micro frontend. Extrai do código-fonte
os artefatos que descrevem a arquitetura, detecta anti-padrões sobre eles
e gera visualizações.

Hoje reconhece **single-spa** e **Module Federation**. Outras tecnologias
entram como extensão, sem alterar os demais módulos. Plataformas com
integração própria sobre essas duas — OpenMRS 3 (`@openmrs/esm-framework`)
e Open edX (`@edx/frontend-platform`) — ficam fora da análise: os pacotes
construídos sobre elas são pulados, com aviso, e o repositório que é só
isso é recusado, em vez de reconstruído errado.

Nenhuma etapa da análise usa modelo de linguagem, rede ou execução do
código analisado. Ver [docs/architecture.md](docs/architecture.md).

## Instalação

```bash
cd mfad
pipx install -e .
```

O `-e` deixa a instalação editável: mudanças no código valem na hora. O
comando `mfad` fica disponível globalmente.

### Testes

```bash
cd mfad
python -m venv .venv && .venv/bin/pip install -e ".[test]"
.venv/bin/python -m pytest
```

Cada teste monta um repositório mínimo numa pasta temporária e roda a
reconstrução inteira sobre ele. Os exemplos são escritos a partir da
documentação de cada tecnologia, não copiados dos sistemas do estudo:
o teste prova a regra, não a forma de um projeto.

## Uso em cinco minutos

```bash
mfad analyze /caminho/do/repo --prefix @sua-org/
```

Reconstrói, detecta e visualiza numa passada, gravando em `artifacts/`.
Os três passos também existem em separado, para quem precisa deles:

```bash
mfad reconstruct /caminho/do/repo --prefix @sua-org/ --out artifacts
mfad detect artifacts --out artifacts
mfad visualize artifacts --detections artifacts
```

Para depurar um extrator, `--only` recorta uma coleção:

```bash
mfad reconstruct /caminho/do/repo --prefix @sua-org/ --only navigations
```

Saída típica:

```
4 micro frontends, 4 fragmentos, 12 telas, 4 imports e 18 navegações
  e 0 comunicações entre micro frontends · 16 chamadas externas
  · 8 acessos ao estado global

nano-frontend  [tamanho]
  monolito tem 1 telas e 0 fragmentos, somando 1, no máximo 5 (piso absoluto).
```

## Os três módulos

| módulo | comando | o que faz |
|---|---|---|
| reconstrução | `reconstruct` e os parciais | lê o código, produz artefatos |
| detecção | `detect` | aplica regras sobre os artefatos |
| visualização | `visualize` | desenha artefatos e detecções |

A detecção e a visualização nunca leem código-fonte. Trabalham só sobre o
modelo de artefatos, e por isso independem da tecnologia de origem.

---

## Comandos

### `reconstruct` — extrai todos os artefatos

```bash
mfad reconstruct <repo> [--prefix PREFIX] [--framework FRAMEWORK] [--out DIR]
```

| opção | padrão | descrição |
|---|---|---|
| `--prefix` | nenhum | filtra os micro frontends pelo prefixo da organização, ex.: `@nabstore/` |
| `--framework` | detectado | força um extrator. Hoje só `single-spa` |
| `--out` | `artifacts` | diretório de saída |

### Extrações parciais

Cada etapa roda sozinha e imprime no terminal, sem gravar:

```bash
mfad microfrontends <repo>     # inventário: rotas, telas, fragmentos, tamanho
mfad compositions <repo>        # quem usa componente de quem
mfad navigations <repo>        # quem leva o usuário para onde
mfad api-calls <repo>          # quem chama qual serviço externo
mfad global-state <repo>       # quem lê qual fatia do estado global
mfad communications <repo>     # quem manda mensagem para quem
```

Todas aceitam `--prefix` e `--framework`.

### `detect` — aplica as regras

```bash
mfad detect [artifacts] [--rule NOME] [--out DIR]
```

| opção | padrão | descrição |
|---|---|---|
| `artifacts` | `artifacts` | diretório com os artefatos |
| `--rule` | todas | aplica só esta regra. Pode repetir |
| `--out` | nenhum | grava `detections.json` |

### `visualize` — desenha

```bash
mfad visualize [artifacts] [--format FORMATO] [--detections ARQUIVO] [--out ARQUIVO]
```

| formato | saída |
|---|---|
| `html` | relatório único, autocontido, sem CDN |
| `features` | sumarização em Markdown do sistema |

Os números do cabeçalho do `html` são também as abas da página. A
primeira caixa, **Dashboard**, abre os grafos; cada número abre a tabela
completa do que ele conta — micro frontends, telas, navegações,
composições (com os fragmentos, numa tabela só), comunicações,
endpoints de API e anti-padrões —, com filtro de texto e ordenação por coluna.
As fatias do estado global compartilhado não têm aba: ficam no
detalhe da detecção `global-state-communication`, com quem lê, quem
grava e onde.
A linha mostra só o que identifica o item; clicar nela abre o resto —
arquivos e linhas, telas, mecanismo — e um atalho para o item no grafo.

O dashboard tem um grafo por pergunta, cada um no seu card, um embaixo
do outro, e só os que têm o que mostrar:

| grafo | o que desenha |
|---|---|
| Visão geral | micro frontends e as relações entre pares: montagem, composição, navegação, comunicação |
| Composição, Navegação, Comunicação | uma relação de cada vez, só com quem participa dela |
| Estado global | cada fatia compartilhada como nó, ligada a quem a lê ou grava |
| Backend | cada endpoint chamado por mais de um micro frontend, ligado a quem o chama |
| Telas | em que tela cada composição, comunicação e navegação acontece, com recorte por micro frontend |

A busca e os filtros do topo valem para todos os grafos. Passar o
mouse num nó destaca as relações dele em todos os grafos; clicar fixa
o destaque e abre os detalhes numa barra lateral à direita, que fecha
no ×, no Esc ou num novo clique no mesmo nó. Na barra, o nome de outro micro
frontend abre ele ali mesmo (o ← volta), e o ↗ ao lado de cada item
leva à aba que o detalha, com a linha dele aberta. Cada card tem o próprio zoom (Ctrl/⌘ +
roda ou os botões), e **ampliar** o deixa mais alto; arrastar o
fundo move. `#view=screens&mfe=<id>&lang=en` no fim do endereço leva
direto a um grafo, num recorte e num idioma; `#page=navigations` abre
direto numa tabela.

A página tem um seletor PT/EN no cabeçalho. Todo texto dela — e as
mensagens das detecções — vem de
`src/mfad/adapters/driven/i18n/texts.json`, com cada chave nos dois
idiomas lado a lado. O título é `<nome da arquitetura> - MFAD`.

### `setup-communication`

```bash
mfad setup-communication <repo>   # gera .mfad/communication.yml
```

---

## Artefatos produzidos

| arquivo | conteúdo |
|---|---|
| `manifest.json` | o envelope: versão do esquema, procedência e índice |
| `microfrontends.json` | os nós: rotas, papel, telas, fragmentos, tamanho |
| `compositions.json` | consumo de componente entre micro frontends |
| `navigations.json` | navegação do usuário entre micro frontends |
| `communications.json` | troca de mensagens |
| `api_calls.json` | chamadas a serviços externos, com as telas que as alcançam |
| `state_accesses.json` | leituras do estado global |
| `detections.json` | gravado pelo `detect` |

Todas as coleções são gravadas a cada execução, inclusive as vazias —
senão o arquivo da execução anterior permaneceria e a etapa seguinte
leria dado que não corresponde mais ao código.

### O envelope

O `manifest.json` é o que torna o conjunto autodescritivo e o
resultado reproduzível:

```json
{
  "mfad": "1.0.0",
  "tool_version": "0.1.0",
  "generated_at": "2026-10-03T14:22:10Z",
  "project": "mfe-hands-on",
  "reconstructor": "single-spa",
  "sources": [
    {
      "path": "mfe-checkout",
      "remote": "https://github.com/org/mfe-checkout.git",
      "commit": "a1b2c3d...",
      "dirty": false
    }
  ],
  "artifacts": {
    "microfrontends": { "file": "microfrontends.json", "count": 6 }
  }
}
```

`mfad` é a versão do **esquema** dos artefatos e sobe quando a forma
dos arquivos quebra quem os lê; `tool_version` é a da **ferramenta**.
São separadas porque corrigir um bug num extrator muda a segunda e não
a primeira — e uma coleta longa precisa poder afirmar que todos os
resultados seguem o mesmo esquema.

`sources[]` lista os repositórios lidos, procurados até dois níveis
abaixo da raiz — é como o `mfad setup` é usado, numa pasta com vários
clones. O `commit` é o que permite repetir a análise sobre exatamente o
mesmo código; `dirty` avisa que havia alteração não commitada e que,
portanto, o `commit` *não* identifica o que foi lido. Credencial
embutida na URL de origem é removida antes de gravar.

Sem git instalado ou fora de um repositório, `sources` vem vazio e a
análise segue normalmente.

A saída é JSON e a entrada é YAML, de propósito: `.mfad/*.yml` é
escrito à mão e ganha comentários; `artifacts/*.json` é gerado e
consumido por máquina. O porquê está em
[docs/decisions.md](docs/decisions.md), seção 9.

### Como os artefatos são descobertos

**Micro frontends** vêm do `registerApplication` do orquestrador — o
contrato do single-spa. Isso encontra também aplicações sem pacote
próprio. Quem não é registrado com nome literal é achado pelos ciclos de
vida que exporta (`bootstrap`, `mount`, `unmount`).

**Rotas** vêm do `activeWhen`; do **single-spa-layout**, tanto no
`<template id="single-spa-layout">` da página quanto no arquivo
`microfrontend-layout.html` que o `create-single-spa` gera; e, no
Angular, do `APP_BASE_HREF` que o single-spa-angular manda declarar. O
nome no layout é ligado ao pacote quando os dois são iguais ou iguais
sem o escopo (`@org/catalog` ↔ `catalog`). O pacote que declara o layout
é o orquestrador.

**Fragmentos** são os exports do entrypoint que não fazem parte do
contrato de lifecycle.

**Telas** vêm do roteador de cada unidade: React Router v6/v7 em JSX
(`element`), em objeto (`createBrowserRouter`, `useRoutes`, `lazy`) e v5
(`component`, `render`, filho); @reach/router; e Angular Router. Rotas
aninhadas somam o caminho do pai. Sem roteador, a tela é o componente
raiz.

**Tamanho** é medido durante a mesma varredura, com as linhas de
comentário descontadas pela árvore sintática — não por prefixo de texto.

**Navegações** usam uma inversão: em vez de procurar chamadas de
navegação, que variam por roteador, o extrator procura expressões que
resolvem para uma rota de OUTRO micro frontend. O dono da rota vem do
`activeWhen`, que é padronizado. O destino de um link do React Router
(`<Link to>`, `<NavLink to>`, `<Navigate to>`, `navigate()`,
`history.push()`) parte do `basename` do roteador da unidade, como o
React Router resolve: debaixo de `basename="/loja"`, `to="/"` é `/loja`.

**Chamadas externas** são reconhecidas em camadas: `fetch` e
`XMLHttpRequest`, que são API da plataforma web; clientes conhecidos
— axios, ky, got, superagent — identificados pelo especificador do
import, incluindo instâncias de `axios.create()`, mesmo criadas noutro
módulo do projeto; o `HttpClient` do Angular, identificado pelo tipo
com que é injetado (`constructor(private http: HttpClient)` ou
`inject(HttpClient)`); e as **funções do projeto que repassam um
parâmetro como URL** a um desses clientes — `fetchApi(url)`,
`this.request.get(endpoint)` —, seguidas em camadas, com o verbo vindo
das opções que quem chama passa. URL que começa por uma base
desconhecida — `` `${API_URL}/users` ``, `API_URL + "/users"` — vale o
caminho depois dela; trecho de runtime no meio vira `{param}`
(`/account/{param}/statement`), e a consulta (`?page=2`) não faz parte
do caminho. A URL guardada numa variável ou devolvida por uma função
do projeto (`const url = statementUrl(id)`) é seguida. Cada chamada
registra as telas que a alcançam seguindo os imports internos — e, no
Angular, os componentes que o template usa pelo seletor, que a tela
renderiza sem importar.

**Imports** seguem a resolução do bundler — extensão implícita e
`/index` — e, para especificador sem ponto, o `baseUrl` e os `paths`
do `tsconfig.json` ou `jsconfig.json` mais próximo, com `extends`.
Apelido que aponta para outro pacote é fronteira, como import de pacote.

**Estado global** vem de bibliotecas conhecidas pelo import — react-redux,
zustand, jotai, recoil, mobx, pinia — e do armazenamento do navegador,
`localStorage` e `sessionStorage`. Nas bibliotecas, só **leitura**: o
seletor percorre o caminho explicitamente, enquanto a escrita revela
apenas o nome da ação. No armazenamento, leitura e escrita, porque as duas
dizem a chave. Store Redux criado dentro da própria unidade é estado
local dela e não entra. Função do projeto que repassa um parâmetro seu
como chave — `setLocalStorageItem(key, value)`, um `LocalStorageService`
injetado no Angular — vira acesso ao armazenamento, com a chave lida em
quem chama, e o acesso é de quem chama: o utilitário pode morar num
pacote comum. Acesso em função sem uso não conta.

**Arquivos de teste não são lidos**: `*.spec.*`, `*.test.*` e as pastas
`__tests__`, `__mocks__`, `cypress` e `e2e`.

**Comunicação** tem três camadas: primitivas da plataforma
(`CustomEvent` com `dispatchEvent`/`addEventListener` — também o evento
criado numa variável antes de disparado —, `fromEvent(window, …)` do
rxjs, `BroadcastChannel`), barramentos conhecidos por import, e o
mecanismo declarado pelo usuário. Ponta dentro de função sem uso não
conta: função não exportada que nada no arquivo referencia, ou função
exportada de um arquivo que o projeto importa sem trazer esse nome.

**Dono do código** é a unidade cujo diretório contém o arquivo, o mais
longo que casar. Código fora de qualquer unidade — pacote compartilhado,
ferramenta — não é de ninguém e não gera aresta.

---

## Declarações por projeto

Ficam em `.mfad/`, na raiz do repositório analisado — versionadas com
ele, e imunes à limpeza da pasta de saída.

### `.mfad/communication.yml`

Rotas e fragmentos são extraídos sem configuração porque a tecnologia
padroniza esses contratos. Comunicação por mecanismo próprio não tem
padrão, e é declarada:

```yaml
mechanisms:
  - name: eventos
    kind: pubsub
    produce:
      module: "@sua-org/utils"    # especificador do import, literal
      export: publishEvent        # nome EXPORTADO, não o nome local
      channel_argument: 0         # posição do canal, base 0
    consume:
      module: "@sua-org/utils"
      export: subscribeToTopic
      channel_argument: 0
```

Produtor e consumidor são pareados pelo **valor do canal**.

> Zero comunicações com declaração preenchida quase sempre significa
> `module` que não bate com o especificador real do import.

---

## Regras de anti-padrão

Sete, de 27 do catálogo. A triagem completa está em
[docs/catalogue.md](docs/catalogue.md).

### `cyclic-dependency`

Micro frontends que dependem uns dos outros em ciclo **dentro de uma
mesma tela**. Estar na tela é ser alcançado por ela: o código que o
componente da tela importa e os fragmentos que ela renderiza, em
qualquer profundidade. Num grafo do sistema inteiro, arestas de telas
diferentes se encadeavam e, em sistema grande, os ciclos explodiam sem
que nenhum fosse montado de fato.

Avalia composição e comunicação **separadamente**, porque um ciclo
significa coisas diferentes em cada uma. Navegação não entra: ela liga
uma tela a outra, e ida e volta entre telas é fluxo do produto. Uma
ocorrência por ciclo, com as telas em que ele aparece.

### `hub-like-dependency`

Tela que instancia muitos fragmentos. O sinal é a quantidade de
**fragmentos distintos**, não de provedores nem de instanciações: cinco
fragmentos de um provedor só concentram tanta mudança de contrato quanto
cinco de cinco, e o mesmo fragmento repetido numa lista é um só. Padrão 5.

### `one-for-all`

Micro frontend ligado a quase todos os demais. Conta vizinhos sem
direção, mas registra separadamente de quem depende e por quem é
dependido — gargalo compartilhado e excesso de conhecimento são
problemas distintos. Exclui o orquestrador, se abstém em sistemas
pequenos e ignora as arestas simétricas do estado global, que ligariam
todos a todos — esse acoplamento é do `global-state-communication`.

### `hammering-apis`

Rota de serviço consumida por mais de um micro frontend. Agrupa por
**caminho**, não por caminho mais método: quem lê e quem escreve no
mesmo recurso compartilham o mesmo contrato.

### `global-state-communication`

Estado global acessado por mais de um micro frontend — fatia de store ou
chave de `localStorage`/`sessionStorage`. Ocorrência **única e binária**:
o sistema usa estado como canal ou não usa.

### `mega-frontend`

Micro frontend cujas telas **e** linhas de código ficam acima de `2×` a
mediana do sistema. Indica concentração de responsabilidades, mas não
prova: uma unidade grande e coesa não é um Mega Frontend.

### `nano-frontend`

Micro frontend com poucas telas somadas a fragmentos — até 5, ou abaixo
da cerca inferior de Tukey do sistema — **e** menos código que a
mediana do sistema. A segunda condição é a mesma exigência dupla do
`mega-frontend`: poucas telas com muito código é tela densa, não unidade
pequena. Indica fragmentação excessiva, mas não prova: uma unidade
pequena é legítima quando constitui sozinha uma capacidade inteira.

### Sem escala de severidade

Atribuir "alta" ou "baixa" exigiria um critério definido e justificado.
No lugar, cada ocorrência informa a **dimensão** — qual relação
arquitetural a produziu.

---

## Limitações conhecidas

**Propagação de constantes** é indexada pelo nome do identificador,
globalmente. Dois arquivos com uma `const routes` diferente colidem. Na
constante simples (`const KEY = "x"`), um nome com dois valores no
repositório não resolve.

**Nome no layout diferente do pacote** só é ligado quando difere pelo
escopo. `@org/argo-gestao` e um pacote `gestao` ficam sem ligação.

**Vue Router e arquivos `.vue`** não são lidos.

**Apelido de import do bundler** (`resolve.alias` e `resolve.modules`
do webpack, `alias` do Vite) não é lido; só o do `tsconfig`/`jsconfig`.

**Código morto** é descartado nas pontas de comunicação, nos acessos
ao estado global e nas chamadas a API, só no nível de função. Arquivo
que ninguém importa conta como vivo — pode ser entrada da aplicação ou
módulo exposto —, e método de classe também.

**Chave de storage por embrulhadora** só é seguida quando é o
parâmetro, com no máximo texto fixo antes e depois. Chave dentro de
objeto (`storage.get({ key })`), método escolhido em runtime
(`storage[op](key)`) e utilitário importado pelo nome do pacote do
workspace (`@org/utils`, sem `paths` no `tsconfig`) ficam de fora.

**`basename` do roteador** vale para todos os links da unidade quando
ela declara um só valor. Com dois roteadores de bases diferentes, o
destino fica como está escrito.

**`activeWhen` como função** não é resolvível estaticamente.

**Destino de navegação dinâmico** (`navigate(variavel)`) não resolve.
Literais, constantes, templates e `.replace(":id", …)` resolvem.

**Navegação dentro de fragmento** é atribuída ao micro frontend que
define o fragmento, não ao que o renderiza.

**Unidades montadas lado a lado** pelo orquestrador, sem que uma
renderize a outra, não estão na mesma tela para o `cyclic-dependency` —
nem o `customProps`, que é emitido no registro. Fica de fora por
definição.

**Escrita no estado global** não é extraída: a chamada revela o nome da
ação, não a fatia alterada.

**`baseURL` não resolve**, porque vem de variável de ambiente. Os
caminhos ficam relativos, e dois micro frontends falando com serviços
diferentes no mesmo caminho parecem iguais.

**Função que embrulha um cliente** só é seguida quando a URL TERMINA no
parâmetro, com no máximo base e texto antes (`${base}${url}`). Se o
texto antes já é caminho (`"/api/" + endpoint`), a chamada fica onde
está, como `/api/{param}`. Função guardada em variável, objeto de
serviço montado em runtime e injeção sem tipo escrito não têm alvo.

**GraphQL não cabe no modelo** de chamada externa: tudo vai para um
endpoint só, e a unidade real é a operação.

**Mudar uma declaração exige refazer o `reconstruct`.** Editar
`communication.yml` e rodar só o `detect` usa a resolução anterior, sem
aviso.

**Versões do tree-sitter estão fixadas numa faixa fechada.** O núcleo e
os bindings de linguagem compartilham uma ABI, e misturar famílias
corrompe memória silenciosamente — o processo morre por falha de
segmentação em lugares aleatórios, sem exceção.
