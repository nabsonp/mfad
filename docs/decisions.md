# Decisões de projeto do MFAD

Documento vivo. Uma entrada por decisão, com a razão. Decisão
revertida fica registrada como revertida, não some.

Última atualização: 03/10/2026.

---

## 1. Escopo e arquitetura

**Três módulos independentes** — reconstrução, detecção, visualização.
A reconstrução é extensível por tecnologia; a detecção é agnóstica,
opera só sobre artefatos.

**Arquitetura hexagonal por módulo**, não uma para o todo. Permite usar
só a reconstrução sem arrastar o resto.

**`composition.py` é o único ponto de composição.** Nenhum adaptador
instancia outro.

**Casos de uso separados por extração**, agrupados em subpastas por
módulo. Um `reconstruct` monolítico matava a responsabilidade única;
hoje ele só compõe os outros.

**Um arquivo de artefato por coleção.** ~~Sem índice ou manifesto: não
havia consumidor para ele.~~ **Revertido em 03/10/2026** — o consumidor
apareceu: a avaliação empírica sobre centenas de repositórios precisa
dizer de qual revisão de qual repositório cada resultado fala. Ver
seção 9.

**Nada de código não solicitado.** Esqueleto primeiro, implementação
sob demanda.

---

## 2. Modelo de domínio

**`MicroFrontend`**, não `Application`. **`AntiPatternDetection`**, não
`Finding`. O vocabulário é o do domínio, não o da ferramenta.

**Severidade removida.** O catálogo de anti-padrões não a define;
inventar uma escala seria contrabandear julgamento para dentro do dado.

**Domínios são artefato**, com hierarquia de subdomínios. As regras
operam no nível superior, então granularidade do mapa não altera o
resultado.

**Estado global: só leitura.** A escrita também acopla, mas o ponto da
chamada revela o nome da ação despachada, não a fatia alterada —
descobrir a fatia exigiria seguir o redutor. Misturar caminho de estado
com nome de ação seria misturar dois vocabulários. Vale para as
bibliotecas; no armazenamento do navegador a escrita entra (ver abaixo).

**`localStorage` e `sessionStorage` são estado global.** ~~Canal de
comunicação dirigido: `setItem` produz, `getItem` consome.~~ **Revertido
em 08/10/2026.** Quem grava não manda nada a ninguém; deixa o dado para
quem vier, e o acoplamento é o formato do valor sob a chave — o mesmo
de uma fatia de store. Como canal dirigido, o token de autenticação
gravado por um e lido por todos fechava ciclo entre quase qualquer par:
no udistrital eram 844 arestas de `localStorage`, e os 200 ciclos que
estouravam o teto do `cyclic-dependency`. A escrita entra porque aqui
ela diz a chave; `StateAccess.access` separa `read` de `write`.
Esquema 3.1.0 → 3.2.0: as chaves saem de `communications.json` e
entram em `state_accesses.json`.

**A fatia é biblioteca e caminho juntos.** A chave `user` do
`localStorage` e a fatia `user` de um store são dados diferentes.

**Acoplamento por estado global entra no grafo de comunicações**, como
aresta com `mechanism: "global-state"`. Antes era coleção à parte e as
regras de grafo subcontavam o acoplamento real.

**`Communication.directed`** distingue aresta com sentido de aresta
simétrica. Estado compartilhado não tem origem; a simetria é
representada por um par de arestas opostas, e quem percorre o grafo
precisa saber disso.

---

## 3. Determinismo

**Nenhuma etapa da análise usa LLM, rede ou execução do código
analisado.** É o que torna o resultado reproduzível e auditável.

**LLM confinado a etapas de autoria.** Ele ajuda a *escrever* um
arquivo — mapa de domínios, spec de comunicação — que é revisado e
versionado. O MFAD lê o arquivo, não o modelo.

**Artefato gerado por LLM rejeitado como entrada.** Um `features.md`
produzido por modelo não é artefato que o MFAD gera, logo não pode
fazer parte do caminho de análise.

**Chave de API em `~/.config/mfad/`, nunca em `.mfad/`.** A segunda é
versionada junto com o projeto analisado. Arquivo criado com modo
`0600`; a chave nunca é exibida por inteiro.

---

## 4. Reconstrução

**Descoberta parte de `registerApplication`**, não de `package.json`.
Em single-spa o orquestrador declara todos os micro frontends; começar
por ele achou um que a varredura de pacotes não via.

**`--prefix` é obrigatório.** Sem ele o filtro de fragmento abria
(retornava verdadeiro para tudo) e capturava todos os imports.

**`activeWhen` casa por prefixo com fronteira de segmento.** `/` sempre
está montado, mas não é dono de toda URL.

**Navegação por inversão dirigida a alvo.** Em vez de reconhecer a
chamada de navegação — que muda com cada roteador —, reconhece-se a
expressão que resolve para uma rota pertencente a outro micro frontend.
Independe de biblioteca.

**Detecção em camadas**: primitivas da plataforma (universais) →
bibliotecas conhecidas por especificador de import → spec declarada.
Funciona sem declaração nenhuma; a declaração só aumenta a cobertura.

**Avaliação parcial de strings** com propagação de constantes, template
e concatenação. O resultado carrega a confiança: `exact` quando a URL
foi resolvida inteira, `prefix` quando só o começo.

**Atribuição por alcançabilidade** — fecho transitivo dos imports
relativos a partir de tela e fragmento. Revelou que `services/api.js`
é código morto nos três micro frontends do repositório de referência.

**Extensão implícita é acrescentada, não trocada.** `./x.component`
resolve para `x.component.ts`. A resolução trocava o sufixo e tentava
`x.ts`, o que deixava sem arquivo toda a convenção de nomes do Angular
(`.component`, `.service`, `.module`) e a raiz `root.component.tsx` do
template do single-spa. Corrigido em 08/10/2026: no udistrital, as telas
sem arquivo caíram de 241 para 0 (de 251), e os arquivos alcançados por
alguma tela subiram de 10 para 232. Grupo-10, LBHackney e Insta-Graph
ganharam a tela da raiz, que antes não era encontrada.

**No Angular, o template é import.** A tela escreve `<app-tabela>`, e
quem liga o seletor à classe é o `NgModule`: o `.ts` da tela não
importa o filho. O alcance passou a seguir o seletor até o arquivo que
o declara, no mesmo pacote. É a correção que vale para qualquer
aplicação Angular. Ler `baseUrl`/`paths` do `tsconfig` (imports
`src/app/...`) ficou de fora por ser configuração de cada projeto.
Decidido em 08/10/2026.

**Código de teste não é lido.** `*.spec.*`, `*.test.*`, `__tests__`,
`__mocks__`, `cypress` e `e2e` saem da varredura, que é única para
todos os extratores. Teste não é montado em execução: no udistrital, um
`auth.guard.spec.ts` gravando no `localStorage` virava comunicação.

**Correções genéricas, testadas por exemplo escrito da documentação.**
Uma auditoria de 08/10/2026 comparou a saída com o código de 13
sistemas. As correções seguem a API documentada de cada tecnologia ou a
semântica da linguagem, nunca a convenção de um projeto; cada uma tem
um teste em `tests/` com um repositório mínimo escrito a partir da
documentação. Ficaram de fora, por serem convenção de um sistema só: o
`data: { app }` de rota que um orquestrador Angular usa para montar
parcels, e a pasta `src/test/` como código de teste.

**Dono do código é o diretório mais longo que o contém.** Olhar só a
primeira pasta do caminho dava como dono, em monorepo com as unidades
um nível abaixo, a pasta do monorepo. Código fora de qualquer unidade
não é de ninguém e não gera aresta — inclusive chamada externa, que
antes criava consumidor fora do inventário.

**URL depois de base desconhecida vale o caminho.** `${API_URL}/users`
era descartada inteira, e quase toda chamada a serviço é escrita assim.
Navegação continua exigindo URL que começa no próprio caminho: uma base
desconhecida pode ser outra origem. Chave de storage e nome de canal
exigem valor inteiro — `"cart_" + id` não diz qual fatia é.

**Layout do single-spa nas duas formas, e o orquestrador vem dele.** O
`microfrontend-layout.html` do `create-single-spa`, com raiz
`<single-spa-router>`, não era lido — só o `<template>` na página. O
pacote que declara o layout vira o shell, montando o que o layout nomeia.
`<route default>` não dá prefixo. O nome do layout liga ao pacote
quando é igual ou igual sem o escopo; semelhança além disso seria
adivinhar.

**`APP_BASE_HREF` é rota no Angular.** O single-spa-angular manda
declará-lo com o prefixo da montagem. Vale quando nem o registro nem o
layout dão rota, e cobre unidade cujo orquestrador não está no
repositório.

**Rotas do React em todas as formas documentadas**, num leitor próprio
(`routers/react.py`) usado pelos dois extratores: v6 em JSX com
aninhamento relativo, v6.4+ em objeto (`createBrowserRouter`, `lazy`),
v5 (`component`, `render`, filho) e @reach/router.

**Constante simples resolve pelo nome, se o nome tiver um valor só.**
`const CART_KEY = "cart"` — inclusive importada de outro módulo, sem
seguir o import: se o nome só tem um valor no repositório, é ele.

**Evento criado antes de disparado** é seguido até a declaração no
escopo, e `fromEvent(window, …)` do rxjs é ouvinte. Só alvos globais
contam: `fromEvent(botao, "click")` é evento de elemento.

**Declaração de rota não é navegação.** `path` e `from` em `<Route>`,
`<Redirect>` ou filho direto de `<Router>`/`<Routes>`/`<Switch>`, e
`basename` num `*Router`, são o roteador dizendo o que responde ali —
mas `path` num componente do projeto (`<Voltar path={routes.HOME}>`)
leva a algum lugar, e fica. `fetch(url)` busca dado, e argumento de
método de texto (`url.endsWith("/")`, `split("/")`) é texto.

**Aplicação fora de `<route>` no layout não tem rota.** Fica sempre
montada e não é dona de URL; com a rota `/`, todo `"/"` do código virava
navegação para ela — 191 no udistrital.

**Caminho de serviço precisa de um segmento literal.** `/` sozinho, de
`${base}/${rota}`, não nomeia serviço e juntaria tudo numa rota só.

**Nome de `registerApplication` só literal.** O texto de um
identificador virava nome de aplicação (`appName`).

**Store Redux criado na própria unidade é local.** Duas unidades com
`createStore` cada e a mesma fatia não compartilham nada.

**Import feito só pela entrada avulsa de um remoto não é composição.**
O hospedeiro carrega o que o remoto publica; o `main.tsx` do remoto só
roda com ele aberto sozinho. Fazia uma biblioteca de componentes,
usada apenas ali, parecer dependida por todos no `one-for-all`.

**Pacotes de plataforma com integração própria saem da varredura.**
OpenMRS 3 e Open edX usam single-spa/MF por baixo e registram as
aplicações em tempo de execução, por manifestos próprios. O extrator os
reconhecia e devolvia inventário enganoso. O corte é por pacote, como o
de teste: o que depende da plataforma, ou é ela (`@openmrs/esm-*`),
fica de fora, com aviso no CLI, e o resto segue — o Bahmni tem um
módulo OpenMRS ao lado de duas unidades de Module Federation. Quando
não sobra nada, a resposta é "não suportado".

**Varredura podada, não `rglob`.** Descer em `node_modules` levava
minutos; podar levou a 3,3s.

**Função que repassa a URL é cliente HTTP.** O padrão mais comum de
chamada a serviço é a função própria — `fetchApi(url)`, um
`RequestManager` no Angular — e a URL só aparece em quem a chama. O
critério é fluxo de dado, não nome: a função vira cliente quando passa
um parâmetro seu como URL de um cliente conhecido, e isso se propaga
em camadas. Só quando a URL TERMINA no parâmetro, com no máximo base e
texto antes; `"/api/" + endpoint` já é caminho e fica onde está — não
dá para saber o que o parâmetro completa, e a regra antiga não perde
nada.

**`HttpClient` do Angular pelo tipo injetado.** O import do módulo não
basta — `@angular/common/http` também exporta `HttpHeaders` e
`HttpParams` —, e a chamada é sempre sobre a instância (`this.http`).
O tipo escrito no parâmetro de construtor ou no `inject(HttpClient)` é
o que o próprio compilador usa para saber o que `http` é.

**Trecho de runtime no caminho vira `{param}`, e a consulta sai.**
Cortar no primeiro `${}` juntava `/account/${id}/statement` e
`/account/${id}/transfers` em `/account/` no `hammering-apis`. O
caminho guarda o que vem depois; `?page=2` não muda o contrato.

**`paths` e `baseUrl` do `tsconfig`.** São a regra do compilador, e os
projetos TypeScript importam quase tudo por apelido (`@/utils/x`). Sem
eles o alcance parava na tela e o código morto não tinha como ser
decidido. Apelido que aponta para outro pacote é fronteira, como import
de pacote. Os apelidos do bundler (`resolve.alias`, Vite) ficam de
fora: estão em código de configuração, não em dado.

**Ponta de comunicação em função sem uso não conta.** Três unidades do
Grupo-10 tinham uma cópia de `setAccountId` que dispara o evento, e
nenhuma a chamava — o arquivo era importado só por `getAccountId`. A
regra é a de "símbolo sem uso" dos linters, conservadora: arquivo que
ninguém importa e método de classe contam como vivos, porque o
consumidor pode ser o framework.

**Função que repassa a chave é acesso ao storage.** É o mesmo padrão do
`fetchApi`: `setLocalStorageItem(key, value)` no Grupo-10, um
`LocalStorageService` no gematik, um `LocalStorageUtil` no Bahmni. A
chave só aparece em quem chama, e sem seguir a função o acesso sumia.
O acesso é atribuído a QUEM CHAMA, não ao arquivo da função: o
utilitário costuma morar num pacote comum, que não é de unidade
nenhuma, e são as unidades que o usam que se acoplam pela chave. O
reconhecimento das embrulhadoras em camadas é o mesmo das chamadas
HTTP, num módulo comum (`forwarding.py`). A chave continua tendo de
ser inteira — `` save(`cart_${id}`) `` não vira fatia.

**Acesso ao estado global em função sem uso não conta**, pelo mesmo
critério das pontas de comunicação. O `setAccountId` sem uso do
Grupo-10 gravava no `localStorage` e contava como acesso.

**Chamada a API em função sem uso também não conta**, pelo mesmo
critério. Chamada que nunca sai do navegador não acopla a unidade ao
serviço e não pode compor um `hammering-apis`.

**Link do React Router parte do `basename`.** `<Link to="/">` debaixo
de `basename="/loja"` vai para `/loja`; lido como absoluto, virava
navegação para o dono de `/`. Vale quando a unidade declara uma base
só: com duas, não se sabe de qual roteador é cada link.

---

## 5. Extensão por tecnologia — decidido, não implementado

**Setup por entrevista.** Um agente pergunta ao usuário como são feitas
composição, roteamento e comunicação entre os micro frontends, pedindo
exemplos de código ou descrição em texto.

**O agente gera dado, não código.** A saída é uma spec declarativa,
não um extrator. O caminho de análise lê arquivo versionado em vez de
executar código gerado por modelo; trinta linhas de YAML são revisáveis
de verdade, trezentas de extrator não são; e quem replica a pesquisa lê
a spec.

**A spec fica em `.mfad/`**, versionada com o projeto analisado, junto
do `domains.yml`. Quem clona o repositório reconstrói sem refazer a
entrevista.

**Os algoritmos continuam no motor.** Avaliação parcial, alcançabilidade
e inversão dirigida a alvo já são agnósticos. A spec cobre só o
reconhecimento: qual chamada declara uma unidade, onde estão o nome e a
rota. A superfície é pequena de propósito.

**Mecanismos coexistentes: aplica todos e junta.** Um repositório pode
usar single-spa e Module Federation ao mesmo tempo. Sem precedência e
sem condicional — a spec não vira linguagem de programação.

**Valor não resolvido retorna vazio.** A spec só enxerga o que está na
própria chamada; `registerApplication(config)` com o objeto montado
noutro lugar fica de fora. Começar pequeno: sem relato de cobertura,
sem aviso. Se virar problema na prática, RF-25 trata.

**Falta um detector de tecnologia.** Hoje o MFAD pressupõe single-spa
em vez de descobrir. O registry de reconstrutores existe, mas ninguém
escolhe entre eles.

---

## 6. Detecção

**Regras agnósticas de tecnologia**, operando só sobre artefatos. Uma
regra nova não conhece single-spa.

**Regras adicionadas uma a uma**, com verificação em código real a cada
uma.

**Tamanho como evidência**, e como critério de decisão apenas quando
não há mapa de domínios.

**`cyclic-dependency` ignora arestas simétricas.** Procurar ciclo numa
relação sem sentido encontra um em toda dupla de leitores — o ciclo
seria a codificação, não o sistema. O teste é `directed`, não o nome do
mecanismo, para que qualquer meio simétrico futuro já entre certo.

**`nano-frontend` exige também código abaixo da mediana.** O piso de
5 telas e fragmentos, sozinho, acusava a maior unidade do udistrital.
Decidido em 08/10/2026.

**`hub-like-dependency` conta fragmentos distintos**, não sítios de
renderização: o mesmo card numa lista é uma dependência só.

**`one-for-all` também ignora arestas simétricas.** Com o
armazenamento do navegador virando estado global, a chave do token
ligou quase todo micro frontend a todos os outros, e no udistrital a
regra passou de 6 para 43 acusações. O acoplamento é real, mas não tem
centro, e já é do `global-state-communication`. Decidido em 08/10/2026.

**`cyclic-dependency` procura ciclo dentro de uma tela.** ~~Um grafo
por relação, do sistema inteiro.~~ **Revertido em 07/10/2026** — em
sistema grande, arestas de telas diferentes se encadeavam e o número
de ciclos explodia sem que nenhum fosse montado de fato. Agora há um
grafo por relação e por tela, e o mesmo ciclo em várias telas é uma
ocorrência só, com as telas listadas.

**Estar na tela é ser alcançado por ela.** Contam o código que o
componente da tela importa e os fragmentos que ela renderiza, em
qualquer profundidade. Micro frontends co-montados pelo `activeWhen`
ficaram de fora de propósito, por ser o recorte mais estrito. O preço
é conhecido: unidade sem `<Route>` não tem tela, e a troca de evento
entre unidades montadas lado a lado — o caso do Grupo-10, que tinha 5
ciclos de comunicação — deixa de aparecer.

**Navegação saiu do `cyclic-dependency`.** Ela liga uma tela a outra;
ida e volta entre telas é fluxo do produto.

**A reconstrução grava onde cada coisa acontece.** `RenderLocation`
ganhou `fragments` — o aninhamento, que `screens` não via porque a
alcançabilidade não atravessa a fronteira do pacote — e `Communication`
ganhou `produced_on` e `consumed_on`. Esquema 3.0.0 → 3.1.0: só campos
novos, mas artefato antigo, lido com eles vazios, não acusa ciclo
nenhum em silêncio.

---

## 7. Visualização

**Relatório HTML autocontido**, com quatro níveis de leitura.

**Uma visão por pergunta, não um grafo com tudo.** O círculo com
todas as relações deixava de ser lido a partir de umas vinte unidades:
no udistrital, 53 nós sobrepostos e 4.468 arestas. A maior parte
eram pares de estado global — uma chave lida por N unidades vira N²
arestas —, e as arestas de endpoint compartilhado tinham o mesmo
defeito. As duas viraram desenhos bipartidos, com o que é
compartilhado como nó: uma ligação por participante. As relações
entre pares ficam na visão geral e num grafo por relação, cada um só
com quem participa.

**Força dirigida por componente, em Python, sem semente.** A posição
inicial vem da ordem dos identificadores e o número de iterações é
fixo: o mesmo artefato dá o mesmo desenho. Componentes são arranjados
à parte e empacotados; quem não tem relação no recorte vai para uma
faixa própria, em vez de empurrar os outros. A sobreposição de
rótulos é removida depois, pelo eixo de menor conflito.

**Telas como lugar das relações.** A composição já sabia em que tela
o fragmento é instanciado e a comunicação, em que tela cada ponta
está; a navegação passou a saber de que tela parte (`on`, esquema
3.3.0), e o destino é a tela cuja rota recebe a URL. A visão de telas
põe os micro frontends em camadas no sentido do fluxo — quem publica
ou navega à esquerda de quem recebe —, para as arestas não
atravessarem molduras. Ponta em código que nenhuma tela alcança fica
como "fora de tela": a relação existe, só não tem lugar na interface.

**Recorte por micro frontend pré-calculado.** Com dezenas de unidades,
a visão de telas inteira é longa demais para responder "com quem esta
fala, e de onde". Cada recorte é arranjado de novo e vai num
`<template>`, que o navegador só desenha quando escolhido.

**Os números do cabeçalho são abas.** Um número que não se abre pede
confiança; um que leva à lista que o soma se confere. Cada caixa abre
a tabela do que conta, com arquivo e linha de cada item, e a primeira
caixa volta ao mapa. As tabelas, que antes ficavam empilhadas abaixo
do mapa — detecções, endpoints, inventário —, foram para as abas, e a
página inicial ficou só com o mapa e o painel. Fragmentos e composições são uma
tabela só, aberta por uma caixa só, a de composições: a composição é o
fragmento visto de quem o monta, e a linha do fragmento já diz quem o
monta e em que telas. Com duas caixas para a mesma tabela, as duas
ficavam selecionadas juntas.

**Dashboard com todos os grafos.** Com as tabelas nas abas, a
página inicial ficou só com o mapa, e as visões dele eram outra fila
de abas, uma de cada vez. Virou um dashboard: um card por grafo, um
embaixo do outro, na largura toda. Dois por linha foi tentado e
descartado: o card estreito encolhia os grafos grandes demais. A busca e os filtros valem para todos, e o
destaque de um micro frontend acende em cada grafo ao mesmo tempo —
a comparação entre relações, que antes pedia trocar de aba, é a
leitura da página. O zoom é de cada card: fechado, o grafo encolhe até
caber inteiro, para ver a forma; **ampliar** deixa o card mais alto,
onde o texto volta a ser lido.

**Detalhes numa barra lateral que abre no clique.** O painel ficava
sempre ao lado do dashboard, ocupando largura com um texto de ajuda
enquanto nada estava escolhido. Virou uma barra que desliza da direita
só quando se clica num nó, numa aresta ou num atalho, e fecha no ×, no
Esc ou clicando de novo no mesmo nó. Passar o mouse continua só
destacando. A ajuda foi para a barra de busca do topo.

**A barra lateral leva às abas.** Cada item da barra tem um ↗ para a
aba que o detalha: a tela, o fragmento, o endpoint, a detecção, o par
de uma dependência. As linhas das tabelas carregam chaves (`data-key`:
o micro frontend, a tela, o par `origem>destino`, o índice da
detecção), e o link abre a linha certa sem depender de busca por texto,
que acertava linhas a mais. Os números do topo da barra (telas,
fragmentos, anti-padrões) mostram só as linhas daquele micro frontend.
"Rotas" virou "URL base": é o caminho em que o orquestrador monta o
micro frontend, não as rotas das telas.

**Caminhos agrupados por micro frontend.** No detalhe de uma linha, as
localizações (onde a fatia é lida, onde a mensagem é publicada, de onde
o endpoint é chamado, onde o fragmento é importado) vêm em grupos: o
micro frontend uma vez, com o diretório dele, e embaixo os arquivos
sem esse diretório. Repetir `mfe · mfe/src/...` em cada linha
escondia o que muda entre elas, que é o resto do caminho. O caminho
inteiro continua no `title` de cada um.

**Detecção em campos, não numa frase.** Cada regra declara, além da
mensagem, os dados que a sustentam como campos rotulados
(`metadata.text.facts`: telas, fragmentos, limite, linhas, mediana…).
A aba de anti-padrões é uma tabela como as outras: a linha diz o
anti-padrão e quem está envolvido, e o detalhe mostra um campo por
dado, o porquê e o código. A frase com tudo junto obrigava a ler a
sentença inteira para achar um número. A mensagem continua no
artefato e no aviso do mapa; a dimensão também fica no artefato, mas
sai da página, onde só repetia o nome do anti-padrão.

**Estado global compartilhado sem aba própria.** As fatias tocadas por
mais de um micro frontend são exatamente a evidência do
`global-state-communication`; numa aba à parte, a página dizia a
mesma coisa duas vezes, e a detecção só dava a contagem. Agora o
detalhe da detecção mostra cada fatia — biblioteca, chave, quem lê,
quem grava e onde —, e o número do cabeçalho saiu. A visão de estado
global do mapa continua.

**Detecções por rota numa linha só.** O `hammering-apis` emite uma
ocorrência por rota compartilhada, e sistemas com dezenas delas
enchiam a tabela de linhas iguais. A página junta as detecções de
rota (`metadata.path`) do mesmo anti-padrão numa linha, com um bloco
fechado por rota — métodos, quem chama e as chamadas por micro
frontend e arquivo —, como as fatias do estado global. É só
apresentação: o artefato continua com uma ocorrência por rota, e as
contagens não mudam. O "ver no grafo" foca todas as rotas juntas.

**Chamadas externas numa tabela só.** A aba tinha a tabela de
endpoints e, abaixo, uma linha por chamada. O detalhe do endpoint já
tinha cada chamada — micro frontend, arquivo, linha, método e tela —,
e a segunda tabela repetia isso; só o cliente HTTP faltava, e entrou
no detalhe. O trecho de código da chamada saiu: o arquivo e a linha
levam a ele.

**Textos num JSON só, em dois idiomas.** A página e as regras leem de
`i18n/texts.json`, com `pt` e `en` lado a lado em cada chave. O HTML
sai em português com cada texto marcado pela chave e pelos valores, e
o seletor do cabeçalho refaz as frases em inglês sem voltar ao Python
— inclusive dentro dos SVGs e dos recortes guardados. A regra grava a
mensagem em português, como sempre, e a referência no `metadata`
(`text`), que é o que a página traduz; artefato antigo, sem
referência, aparece como foi gravado. As caixas do desenho são medidas
pela versão mais longa das duas.

**Selo, não borda, para anti-padrão.** Num sistema em que quase todas
as unidades aparecem em alguma detecção, a borda vermelha em todas não
distinguia ninguém; o selo diz quantas.

**`visualize` grava arquivo.** O padrão é `html` em
`<artefatos>/architecture.html`. Despejar centenas de kilobytes no
terminal obrigava o usuário a copiar da tela o que o comando já tinha
pronto. `features` (markdown) continua na saída padrão, que é onde
serve.

**Um comando para o caso comum.** `analyze` faz reconstrução, detecção
e visualização numa passada. O encadeamento — `detect` lê o que
`reconstruct` gravou, `visualize` precisa de `--detections` — é detalhe
da ferramenta, não decisão do usuário.

**Seis subcomandos viraram `reconstruct --only`.** `microfrontends`,
`compositions`, `navigations`, `api-calls`, `global-state` e
`communications` eram recorte do mesmo processo exposto como comandos
distintos, e faziam a ajuda listar onze entradas para um fluxo de três
passos. De 11 comandos para 6.

---

## 8. Operação

**Instalação com `pipx install -e`.** Editável, comando global.

**tree-sitter preso à família 0.23.** Núcleo e bindings compartilham
uma ABI; misturar famílias corrompe memória em silêncio e o processo
morre por falha de segmentação em lugares aleatórios, sem exceção.

**`AstReader.walk` é iterativo, com cache de árvore.** Recursão sobre
arquivo grande estourava; a árvore precisa ser mantida viva porque os
nós apontam para a memória dela.

**`save` sempre escreve todas as coleções**, inclusive as vazias.
Pular coleção vazia deixava arquivo obsoleto de execução anterior, e a
detecção seguinte lia dado errado sem qualquer aviso.

---

## 9. Formato e versionamento dos artefatos

**A saída continua em JSON; só a entrada é YAML.** `.mfad/*.yml`
(`communication.yml`, `domains.yml`) é escrito à mão e ganha
comentários. `artifacts/*.json` é gerado e consumido por máquina.
Converter a saída para YAML foi considerado e rejeitado por três
razões. O campo `code` carrega trecho de código-fonte arbitrário —
`:`, `#`, `{`, crase, aspas, quebra de linha — que todo emissor de
YAML resolve quotando, mas o resultado fica frágil justamente para
quem for editar à mão, e a tentação de editar existe porque é YAML.
Determinismo: `json.dumps(indent=2)` produz a mesma saída byte a byte
entre versões, enquanto emissor de YAML varia com versão da
biblioteca, largura de linha e estilo de quoting — e a avaliação
empírica precisa ser reproduzível. Ferramental: `jq` sobre os
artefatos é o uso diário na análise. Legibilidade, o único argumento a
favor, já é resolvida pelo `mfad visualize`.

**O `manifest.json` é um envelope versionado.** Era
`{"project": "..."}`. Passou a carregar versão do esquema, versão da
ferramenta, instante de geração, extrator usado, a revisão de cada
repositório lido e o índice de coleções com a contagem de cada uma.

**Versão do esquema separada da versão da ferramenta.** A chave
`mfad` é o esquema dos artefatos e sobe quando a forma dos arquivos
quebra quem os lê; `tool_version` é a da ferramenta. Separadas porque
corrigir um bug num extrator muda a segunda e não a primeira, e uma
coleta longa precisa poder afirmar que todos os resultados seguem o
mesmo esquema mesmo tendo trocado de versão no meio dela.

**`sources[]` grava `commit` e `dirty` por repositório.** É o que
torna o resultado reproduzível: sem a revisão, um conjunto de
artefatos não diz sobre qual versão do código ele fala, e deixa de ser
verificável assim que o repositório recebe um commit. O `dirty` existe
porque com alteração não commitada o `commit` *não* identifica o que
foi lido — omitir isso produziria procedência falsa, que é pior que
procedência ausente.

**A URL de origem é gravada sem credencial.** Clonar com token na URL
é comum e o remote fica no `.git/config`; copiá-lo para o artefato
publicaria a credencial, porque a saída é versionada. A sonda remove
`usuario:senha@` antes de gravar.

**A procedência vem de uma porta, `SourceProbe`.** Ler o estado do git
é I/O e não pode morar no caso de uso. A implementação `GitSourceProbe`
procura repositórios até dois níveis abaixo da raiz — é como o
`mfad setup` é usado, numa pasta com vários clones — e para de descer
ao encontrar um. Nada ali falha a análise: sem git, a procedência fica
mais pobre e o resto segue.

**O índice de coleções mora no adaptador, não no domínio.** Nome de
arquivo é detalhe de quem persiste. O domínio tem `Provenance` e
`SourceRepository`; o `JsonArtifactRepository` é quem sabe que
microfrontends vão em `microfrontends.json`.

**Manifesto sem a chave `mfad` é aceito na leitura.** Artefato
anterior ao esquema 1.0.0 carrega procedência vazia em vez de ser
recusado — quem precisa da revisão exata checa o campo e encontra
vazio.

**O Open Microfrontends foi avaliado como fonte de inspiração, não
como fundamento.** É uma spec declarativa e prescritiva — o servidor
declara à mão os MFEs que expõe, para que um host saiba carregá-los —
enquanto o MFAD descreve o que foi recuperado do código. Dela vieram
o envelope versionado e a ideia de esquema publicado. Dela *não* vem o
modelo conceitual: ela não tem roteamento, não tem composição, não tem
o conceito de tela e não declara aresta entre MFEs (as mensagens são
pub/sub mediado pelo host), de modo que nenhum dos anti-padrões do
catálogo é detectável sobre um descritor dela. Projeto de um
mantenedor, não padrão de indústria: entra como trabalho relacionado e
possível alvo de exportação.

---

## 10. Roteamento é um eixo próprio

**O leitor de rota não pertence a reconstrutor nenhum.** Integração e roteamento são ortogonais: single-spa e Module Federation dizem como as unidades viram um sistema, React Router e Angular Router dizem como UMA unidade declara suas telas, e qualquer combinação existe. Até aqui o segundo estava cravado dentro do primeiro — `<Route>` do React, duplicado em dois arquivos —, e por isso "rota fora do React Router" parecia limite do Module Federation quando era uma dimensão ausente.

**Unidade Angular saía com zero telas.** No single-spa a rota da unidade vem do `activeWhen`, então o sintoma não era rota faltando, era tela. E tela não é artefato acessório: três regras dependem dela — `hub-like-dependency` conta fragmentos por tela, `access-to-different-domains` resolve domínio por tela, e a atribuição fragmento→tela é construída em cima dela.

**As regras vêm da documentação do framework, não de repositório analisado.** Os sistemas selecionados para o estudo são o conjunto de avaliação; desenvolver contra eles os transformaria em treino e contaminaria qualquer acurácia reportada depois. O leitor de Angular foi escrito a partir da interface `Route` publicada pelo projeto e validado em fixture montado com as formas documentadas. O healthcare-system, usado para construir o reconstrutor de Module Federation, é conta pessoal e não está entre as 14 organizações incluídas.

**`path` do Angular é relativo e precisa ser concatenado.** `path: 'info'` dentro de `path: 'product/:id'` responde por `/product/:id/info`. É a diferença mais consequente para o React Router, onde o caminho aninhado costuma ser escrito absoluto — ler o segmento isolado reportaria uma rota que a aplicação não tem.

**O React Router continua onde está, por ora.** As duas cópias divergiram: a do Module Federation desembrulha `<Suspense>` e resolve o provedor, a do single-spa não. Unificá-las no mesmo passo arriscaria regredir dois extratores que funcionam, sem ganho imediato. Fica como refatoração separada.

---

## 11. Nomes

**`ArtifactSet` virou `MicroFrontendArchitecture`.** O nome antigo descrevia o FORMATO DO RECIPIENTE — "um conjunto de artefatos" — e não a coisa. É a mesma família de `DataManager` e `InfoHolder`: o domínio não deveria saber que aquilo é uma coleção.

O objeto é a arquitetura reconstruída, que é literalmente o que a ferramenta se propõe a produzir. E ele não pertence à reconstrução: é produzido por ela e consumido também pela detecção e pela visualização, então nomeá-lo pelo produtor — `Reconstruction` — leria errado nos outros dois, como se a regra avaliasse o processo em vez da arquitetura.

A variável acompanhou: `artifacts` virou `architecture` em todo lugar onde segura esse tipo. Ficaram de fora, de propósito, os usos em que `artifacts` significa mesmo a PASTA de saída — `arguments.artifacts`, `Path("artifacts")` e a chave `"artifacts"` do manifesto. Ter os dois sentidos com o mesmo nome era parte da confusão.

---

## 12. A v0: sem IA e sem domínio

**Nada de modelo de linguagem, em etapa nenhuma.** Saíram o `mfad setup` com a página web, o `mfad setup-llm`, o repositório de credenciais em `~/.config/mfad/` e os prompts de autoria. O determinismo deixa de ser uma propriedade defendida por convenção e passa a ser estrutural: não há caminho no código que chame um modelo.

**O domínio de negócio saiu inteiro.** Foram embora `Domain`, `DomainMap`, `DomainDeclaration`, o `.mfad/domains.yml`, o `domains.json` e a resolução que os cruzava com os artefatos. Era a única entrada que exigia conhecimento externo ao repositório, e sustentá-la custava uma etapa de autoria inteira.

**`access-to-different-domains` foi removida.** Era a única regra que dependia só do mapa e, sem ele, devolvia vazio. Restam sete das oito.

**`mega-frontend` e `nano-frontend` passam a ser contagem pura** — telas, fragmentos e linhas contra a mediana do sistema, com o orquestrador fora da comparação. As duas já tinham esse modo como alternativa quando faltava o mapa; agora é o único. O que se perde é poder dizer QUAIS responsabilidades a unidade acumula; o que resta é a consequência observável, e a saída carrega as medianas para quem lê poder discordar.

O mega exige telas **e** linhas acima do limiar, não qualquer uma: muitas telas com pouco código é um menu, muito código com uma tela é uma biblioteca. O nano soma telas e fragmentos, porque as duas formas de entregar interface contam.

**Efeito medido:** o nabstore passou de 3 para 4 ocorrências. A nova é `nano-frontend` no `monolito`, com 1 tela contra mediana de 3 — correta pela regra nova, e antes suprimida pelo modo por domínio.

**O `.mfad/communication.yml` fica.** É declaração determinística, escrita e revisada à mão, e o `setup-communication` que gera o template não usa modelo nenhum.

---

## Pendências conhecidas

| | |
|---|---|
| RF-25 | relatar cobertura e o que não foi resolvido |
| RF-35 | avisar quando os artefatos estão obsoletos — barato agora: basta comparar `sources[].commit` do manifesto com o HEAD atual |
| US-28 | suíte de testes automatizados |
| — | `hub-like-dependency` conta aresta simétrica em dobro |
| — | apresentação conta estado global duas vezes (aresta e acesso) |
| — | reconstrutor para Module Federation: 63% da população amostrada |
| — | esquema JSON publicado dos artefatos, para validação externa |
| — | mover o leitor de React Router para `routers/`, unificando as duas cópias |
| — | `loadChildren` do Angular: seguir a tabela de rotas do outro módulo |
| — | `mfad export --format open-microfrontends` |
| — | calibrar `nano-frontend.floor` contra a base do estudo: em 5 ele acusa 9 das 10 unidades de referência |
| — | `MIN_SAMPLE = 8` para a cerca de Tukey é convenção, não medida |
