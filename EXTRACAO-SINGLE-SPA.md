# Regras de extração — single-spa

O que o reconstrutor de single-spa lê do código-fonte, e sob que
condições. Cada regra em *dado / quando / então*.

Escrito a partir da implementação em
`src/damfe/adapters/driven/reconstruction/singlespa/`. Serve para
conferir o que a ferramenta faz e para escrever o reconstrutor de
outra tecnologia sem reler o código.

Nenhuma regra executa o código analisado, acessa a rede ou consulta
modelo de linguagem.

---

## 1. Descoberta

### 1.1 · Inventário de micro frontends

> **Dado** um repositório
> **quando** houver chamadas a `registerApplication`, na forma de
> objeto `({ name, app, activeWhen })` ou posicional
> `(name, loadingFn, activeWhen)`
> **então** cada chamada é um micro frontend, com `name` como
> identidade e `activeWhen` como rotas.

O `registerApplication` é a fonte de verdade do single-spa sobre
quais aplicações existem — inclusive as que não têm pacote próprio.
Partir do `package.json` perde essas.

### 1.2 · Arquivo de entrada

> **Dado** um micro frontend registrado
> **quando** o `app` carregar um especificador de pacote
> (`() => System.import("@org/mfe-x")`)
> **então** o arquivo de entrada é procurado, nesta ordem, no
> diretório cujo `package.json` declara aquele nome, pela convenção
> `src/{org}-{projeto}.{js,jsx,ts,tsx}`, e depois pelos campos
> `module`, `main` ou `source` do manifesto.

> **Dado** um micro frontend registrado
> **quando** o `app` carregar um caminho relativo
> (`() => import("./monolito")`)
> **então** o arquivo é resolvido a partir do arquivo que declara o
> registro.

É assim que um monolito em migração entra no grafo: ele é aplicação
registrada como qualquer outra, e sumiria se só olhássemos o import
map.

> **Dado** um micro frontend registrado
> **quando** nenhum arquivo de entrada resolver
> **então** ele permanece no grafo, marcado
> `metadata.entrypoint_resolved = false`.

Aplicação registrada com ciclos de vida inline no shell existe.
Sumir é pior que aparecer incompleta.

### 1.3 · Papel no sistema

> **Dado** o arquivo de entrada
> **quando** ele exportar `bootstrap`, `mount`, `unmount` ou
> `update`
> **então** os nomes encontrados vão para `metadata.lifecycles`.

São o contrato do single-spa, e é o que confirma que aquilo é um
micro frontend e não um pacote qualquer.

---

## 2. Composição

### 2.1 · Fragmentos expostos

> **Dado** o arquivo de entrada
> **quando** ele tiver `export` nomeado que não seja ciclo de vida
> **então** cada nome exportado é um fragmento daquele micro
> frontend.

### 2.2 · Contêiner de montagem

> **Dado** o arquivo de entrada
> **quando** houver `domElementGetter` resolvendo para
> `getElementById("x")` ou `querySelector("#x")`
> **então** `metadata.container` recebe o identificador do elemento.

Declarar contêiner significa que o shell reservou um lugar no layout:
aquele micro frontend é encaixado numa página junto de outras coisas.
Quem não declara recebe um `div` que o single-spa anexa ao corpo.

### 2.3 · Consumo de fragmento

> **Dado** o catálogo de fragmentos de todos os micro frontends
> **quando** um micro frontend importar, de outro, um nome que esteja
> nesse catálogo
> **então** registra-se um `FragmentImport` entre os dois.

O catálogo é o que dá precisão: sem ele não há como distinguir um
fragmento de qualquer outro export do mesmo pacote, nem reconhecer
uma instanciação em JSX sem apelar para convenção de nome.

---

## 3. Telas e rotas

### 3.1 · Telas declaradas

> **Dado** um micro frontend
> **quando** qualquer arquivo sob o diretório dele tiver
> `<Route path=… element=… />`
> **então** cada ocorrência é uma tela, com o componente do `element`
> e a rota do `path`.

Busca-se em todos os arquivos, não só nos alcançáveis: a pergunta da
reconstrução é quais telas o micro frontend **define**.

### 3.2 · Tela ligada ou desligada

> **Dada** uma tela declarada
> **quando** o arquivo que a declara for alcançável por imports a
> partir do `rootComponent`
> **então** `reachable = true`; caso contrário, `false`.

Tela declarada em arquivo que ninguém importa existe no código e não
existe em execução. As duas coisas interessam, por motivos
diferentes.

### 3.3 · Micro frontend sem roteador próprio

> **Dado** um micro frontend sem nenhum `<Route>`
> **quando** ele declarar contêiner de montagem
> **então** o `rootComponent` é um **fragmento**.

> **Dado** um micro frontend sem nenhum `<Route>`
> **quando** ele não declarar contêiner
> **então** o `rootComponent` é uma **tela**, cuja rota é a do
> `activeWhen`.

Em single-spa o roteador é o `activeWhen`: registrar num prefixo já
serve aquela rota, e roteador interno só faz falta para servir várias
telas sob o mesmo prefixo. Ausência de `<Route>` não significa
ausência de tela — significa uma tela só.

`activeWhen` permanente (`/`) **não** é usado como sinal: duas
aplicações podem dividir o mesmo `activeWhen` sendo as duas telas.

### 3.4 · Dono de uma URL

> **Dada** uma URL
> **quando** comparada às rotas dos micro frontends
> **então** vence o prefixo mais longo que casar com fronteira de
> segmento.

`/checkout` cobre `/checkout` e `/checkout/cards`, e não cobre
`/checkoutx`. A ordenação por comprimento importa: sem ela o shell,
que costuma registrar `/`, engoliria todas as rotas.

---

## 4. Navegação

### 4.1 · Navegação entre micro frontends

> **Dada** uma expressão que produza uma URL
> **quando** essa URL pertencer a outro micro frontend
> **então** registra-se uma navegação da origem para o dono da rota.

Não existe API padrão de navegação no single-spa — cada projeto usa o
roteador do seu framework, ou um componente próprio. Detectar a
**chamada** não seria genérico; detectar o **destino** é, porque toda
aplicação declara suas rotas no registro. O que aciona a navegação
deixa de importar.

### 4.2 · Confiança da resolução

> **Dada** uma expressão de URL
> **quando** ela for determinada por inteiro estaticamente
> **então** `match = exact`; quando só o começo for estático,
> `match = prefix`.

O que não casar com nenhuma forma reconhecida fica sem resolver, e
isso é resposta legítima — a alternativa seria adivinhar.

---

## 5. Chamadas externas

### 5.1 · Detecção

> **Dado** o código de um micro frontend
> **quando** houver `fetch` da plataforma, ou uso de cliente HTTP
> reconhecido pelo especificador do import
> **então** registra-se uma chamada externa, com o caminho resolvido
> pelo mesmo avaliador parcial das rotas.

### 5.2 · Atribuição a micro frontend e a tela

> **Dada** uma chamada externa
> **quando** for atribuída ao micro frontend
> **então** vale o diretório que contém o arquivo da chamada.

> **Dada** uma chamada externa
> **quando** for atribuída a uma tela
> **então** segue-se o alcance por imports internos a partir da tela.

Projetos embrulham o cliente HTTP num módulo próprio
(`services/api.js`), e esse módulo pertence ao micro frontend que o
contém — a aresta `micro frontend → endpoint` sai correta sem seguir
indireção. Saber qual **tela** chama exige seguir, porque a chamada
mora no módulo de serviço.

---

## 6. Estado global

> **Dado** um import de biblioteca de estado conhecida
> (`react-redux`, `zustand`, `jotai`, `recoil`, `mobx-react-lite`,
> `pinia`)
> **quando** houver leitura que percorra um caminho do estado
> (`useSelector((state) => state.cart)`)
> **então** registra-se um acesso, com biblioteca e caminho.

Identificação pelo especificador do import, não por nome de variável.

> **Dada** uma escrita de estado (`dispatch(addProduto(item))`)
> **então** ela **não** é extraída.

O ponto da chamada revela o nome da ação, não a fatia alterada;
descobrir a fatia exigiria seguir o redutor, que pode nem estar no
repositório. Registrar as duas na mesma lista misturaria caminho de
estado com nome de ação.

> **Dada** uma fatia lida por dois ou mais micro frontends
> **então** derivam-se arestas de comunicação `global-state`, não
> direcionadas, entre todos os pares.

---

## 7. Comunicação

Três níveis, todos produzindo o mesmo artefato. Produtor e consumidor
são pareados pelo **nome do canal**, que é o contrato entre as pontas,
não pela forma da chamada.

> **Nível 1 — primitivas da plataforma.**
> **Dado** qualquer código
> **quando** houver `dispatchEvent(new CustomEvent(canal))` com
> `addEventListener`, ou `BroadcastChannel`, ou `postMessage`
> **então** registra-se comunicação.

São API do navegador: valem em qualquer projeto, sem configuração.

> **Nível 2 — barramentos conhecidos.**
> **Dado** um import de `mitt`, `eventemitter3`, `tiny-emitter` ou
> `pubsub-js`
> **quando** o valor vindo dele for usado para publicar ou assinar
> **então** registra-se comunicação.

Não é heurística de nome: se o módulo importado é `mitt`, o que vier
dele é barramento.

> **Nível 3 — mecanismo declarado.**
> **Dado** um `.damfe/communication.yml`
> **quando** ele declarar módulo, export e posição do argumento do
> canal
> **então** aquelas chamadas passam a ser reconhecidas.

Para o wrapper próprio do projeto, que nenhum catálogo conhece. Sem
declaração o resultado não é vazio: os dois primeiros níveis
continuam valendo.

---

## 8. Limites conhecidos

| | |
|---|---|
| `single-spa-layout` | rotas e slots definidos em HTML de layout não são lidos |
| `customProps` | não extraído |
| Composição em runtime | contêiner criado dinamicamente não é reconhecido |
| Escrita de estado | fora do escopo, ver §6 |
| Contenção de componente | fragmento → tela não é resolvido (US-26) |
| Cobertura | o relatório não diz o que ficou sem resolver (US-25) |
