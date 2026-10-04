# Decisões de projeto do DAMFE

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
com nome de ação seria misturar dois vocabulários.

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
versionado. O DAMFE lê o arquivo, não o modelo.

**Artefato gerado por LLM rejeitado como entrada.** Um `features.md`
produzido por modelo não é artefato que o DAMFE gera, logo não pode
fazer parte do caminho de análise.

**Chave de API em `~/.config/damfe/`, nunca em `.damfe/`.** A segunda é
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

**Varredura podada, não `rglob`.** Descer em `node_modules` levava
minutos; podar levou a 3,3s.

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

**A spec fica em `.damfe/`**, versionada com o projeto analisado, junto
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

**Falta um detector de tecnologia.** Hoje o DAMFE pressupõe single-spa
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

---

## 7. Visualização

**Relatório HTML autocontido**, com quatro níveis de leitura.

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
`fragment-imports`, `navigations`, `api-calls`, `global-state` e
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

**A saída continua em JSON; só a entrada é YAML.** `.damfe/*.yml`
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
favor, já é resolvida pelo `damfe visualize`.

**O `manifest.json` é um envelope versionado.** Era
`{"project": "..."}`. Passou a carregar versão do esquema, versão da
ferramenta, instante de geração, extrator usado, a revisão de cada
repositório lido e o índice de coleções com a contagem de cada uma.

**Versão do esquema separada da versão da ferramenta.** A chave
`damfe` é o esquema dos artefatos e sobe quando a forma dos arquivos
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
`damfe setup` é usado, numa pasta com vários clones — e para de descer
ao encontrar um. Nada ali falha a análise: sem git, a procedência fica
mais pobre e o resto segue.

**O índice de coleções mora no adaptador, não no domínio.** Nome de
arquivo é detalhe de quem persiste. O domínio tem `Provenance` e
`SourceRepository`; o `JsonArtifactRepository` é quem sabe que
microfrontends vão em `microfrontends.json`.

**Manifesto sem a chave `damfe` é aceito na leitura.** Artefato
anterior ao esquema 1.0.0 carrega procedência vazia em vez de ser
recusado — quem precisa da revisão exata checa o campo e encontra
vazio.

**O Open Microfrontends foi avaliado como fonte de inspiração, não
como fundamento.** É uma spec declarativa e prescritiva — o servidor
declara à mão os MFEs que expõe, para que um host saiba carregá-los —
enquanto o DAMFE descreve o que foi recuperado do código. Dela vieram
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

## Pendências conhecidas

| | |
|---|---|
| RF-25 | relatar cobertura e o que não foi resolvido |
| RF-35 | avisar quando os artefatos estão obsoletos — barato agora: basta comparar `sources[].commit` do manifesto com o HEAD atual |
| RF-36 | extrair comunicação via `customProps` |
| US-27 | spec de comunicação gerada por LLM, integrada |
| US-28 | suíte de testes automatizados |
| — | `hub-like-dependency` conta aresta simétrica em dobro |
| — | apresentação conta estado global duas vezes (aresta e acesso) |
| — | reconstrutor para Module Federation: 63% da população amostrada |
| — | esquema JSON publicado dos artefatos, para validação externa |
| — | mover o leitor de React Router para `routers/`, unificando as duas cópias |
| — | `loadChildren` do Angular: seguir a tabela de rotas do outro módulo |
| — | `damfe export --format open-microfrontends` |
