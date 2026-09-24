# Catálogo de anti-padrões — viabilidade e especificação

Triagem dos 27 anti-padrões do [catálogo de anti-padrões de micro
frontends](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/)
(ICOMP/UFAM) contra o que o damfe consegue observar por análise estática,
com a especificação de entrada, detecção e saída de cada um.

| faixa | significado | quantidade |
|---|---|---|
| **A** | já implementado | 8 |
| **B** | viável com os artefatos que já existem | 5 |
| **C** | precisa de extração nova | 11 |
| **D** | fora do alcance da análise estática de código | 3 |

## Os artefatos disponíveis

A coluna *Entrada* de cada regra se refere a estes:

| artefato | campos |
|---|---|
| `MicroFrontend` | id, diretório, entrypoint, rotas, papel, telas, fragmentos, tamanho |
| `Screen` | componente, rota, arquivo, linha |
| `Fragment` | nome, arquivo, linha |
| `FragmentImport` | consumidor, provedor, fragmento, local do import, locais de instanciação, props |
| `Navigation` | origem, destino, expressão, URL resolvida, confiança |
| `Communication` | origem, destino, mecanismo, canal, locais dos dois lados |
| `ApiCall` | micro frontend, método, caminho, cliente |
| `StateAccess` | micro frontend, biblioteca, caminho da fatia lida |
| `Domain` | nome, rotas, endpoints, subdomínios, telas, chamadas, micro frontends |

Toda detecção devolve um `AntiPatternDetection`, com regra, dimensão,
explicação, mensagem, elementos envolvidos, locais no código e metadados
próprios da regra. A coluna *Saída* descreve o que é específico de cada
uma.

---

# A — já implementado

## [Cyclic Dependency](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Cyclic%20Dependency)
> Dois ou mais MFEs dependem um do outro, direta ou indiretamente.

| | |
|---|---|
| **Entrada** | `FragmentImport`, `Navigation`, `Communication` |
| **Detecção** | Monta um grafo dirigido por relação, separadamente, e enumera os ciclos elementares de cada um. Teto de 200 ciclos, porque a enumeração cresce com a quantidade de ciclos, não com o tamanho do grafo. |
| **Saída** | Uma ocorrência por ciclo. `dimension` diz qual relação o produziu; `chain` traz a sequência ordenada; `through` lista o que passa por cada aresta — fragmentos, rotas ou canais conforme a relação. |

As três relações são avaliadas em separado porque um ciclo significa
coisas diferentes em cada uma. Ciclo de composição é acoplamento de
build; ciclo de navegação costuma ser fluxo legítimo do produto.

## [Hub-like Dependency](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Hub-like%20Dependency)
> Uma tela de um MFE integra fragmentos de vários outros MFEs.

| | |
|---|---|
| **Entrada** | `MicroFrontend.screens`, `FragmentImport.renders` |
| **Detecção** | Agrupa as instanciações de fragmento por tela, usando as telas que o sítio de renderização registra. Acusa quando a tela instancia `min_fragments` fragmentos. Padrão 5. |
| **Saída** | Uma ocorrência por tela. Metadados: tela, provedores, fragmentos instanciados. |

O sinal é a quantidade de **fragmentos**, não de provedores: é o
número de peças que a tela precisa montar que a torna um ponto de
convergência, e cinco fragmentos de um provedor só concentram tanta
mudança de contrato quanto cinco de cinco.

Contar provedores distintos, como se fazia, punia o desenho normal:
com biblioteca de componentes compartilhada, qualquer tela que usasse
um componente dela mais um fragmento qualquer já somava dois
provedores.

A ligação fragmento↔tela não é mais pelo arquivo: o sítio de
renderização registra em que telas aparece, seguindo os imports
relativos a partir do componente da tela. Fragmento instanciado num
componente auxiliar é atribuído corretamente, e quando o fragmento é
o próprio componente da rota, a tela é aquela e só aquela.

## [Hammering APIs](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Hammering%20APIs)
> Vários MFEs chamam o mesmo endpoint de forma independente.

| | |
|---|---|
| **Entrada** | `ApiCall` |
| **Detecção** | Agrupa as chamadas por **caminho**, não por caminho mais método: um MFE que lê e outro que escreve no mesmo recurso compartilham o mesmo contrato. Acusa a partir de `min_callers` consumidores. Padrão 2. |
| **Saída** | Uma ocorrência por rota compartilhada. Metadados: rota, métodos observados, consumidores. |

## [Global state communication](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Global%20state%20communication)
> Estado compartilhado viola a segregação e aumenta o acoplamento.

| | |
|---|---|
| **Entrada** | `StateAccess` |
| **Detecção** | Agrupa os leitores por fatia e verifica se alguma é lida por `min_microfrontends` ou mais. Padrão 2. |
| **Saída** | Ocorrência **única e binária** — o sistema usa estado global como canal ou não usa. Metadados: as fatias compartilhadas com quem lê cada uma, e as bibliotecas envolvidas. |

Uma por fatia diria a mesma coisa várias vezes. O que interessa é se a
prática existe e quem participa.

## [One Micro Frontend for all](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/One%20Micro%20Frontend%20for%20all)
> Um único MFE é criado e importado por todos os outros.

| | |
|---|---|
| **Entrada** | `FragmentImport`, `Navigation`, `Communication` |
| **Detecção** | Conta vizinhos distintos de cada MFE, somadas as relações, e acusa quem alcança `ratio` dos demais. Exclui o orquestrador do cálculo e se abstém abaixo de `min_microfrontends`. Padrões 0,9 e 5. |
| **Saída** | Uma ocorrência por MFE. Metadados: cobertura, vizinhos, e a separação entre de quem depende e por quem é dependido. |

**Divergência a resolver.** O catálogo descreve especificamente
*importado por todos* — grau de entrada. A implementação atual conta
vizinhança **sem direção**, o que também acusa o MFE que depende de
todos. São problemas distintos: um é gargalo compartilhado, o outro sabe
demais sobre o sistema. Os dois vão nos metadados, mas a regra deveria
ou restringir-se ao grau de entrada, para aderir ao catálogo, ou declarar
explicitamente que amplia a definição.

O orquestrador é excluído porque alcançar todos é a função dele, e
mantê-lo no cálculo inflaria o grau de todos os demais. O piso de
tamanho existe porque num sistema pequeno estar ligado a todos é o
normal, não o desvio.

## [Mega Frontend](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Mega%20Frontend)
> Um MFE assume várias responsabilidades que deveriam estar separadas.

| | |
|---|---|
| **Entrada** | `Domain`, `MicroFrontend.screens` — ou `.size` sem mapa |
| **Detecção** | Telas do micro frontend caindo em mais de um domínio de topo. Sem mapa, tamanho acima de `size_factor` vezes a mediana. |
| **Saída** | Uma ocorrência por micro frontend, nomeando o domínio dominante e **quais telas destoam, com o domínio de cada uma**. |

A saída nomeia as telas em vez de contar domínios porque uma contagem não
diz o que fazer. `dimension` informa o critério usado: `domínio` ou
`tamanho`.

## [Nano Frontend](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Nano%20Frontend)
> Um MFE criado com apenas algumas telas ou fragmentos.

| | |
|---|---|
| **Entrada** | `Domain`, `MicroFrontend.screens` — ou `.size` sem mapa |
| **Detecção** | Todas as telas num único domínio que **outro** micro frontend também serve, e serve `dominance` vezes mais. Sem mapa, tamanho abaixo de `size_factor` vezes a mediana. |
| **Saída** | Uma ocorrência por micro frontend, nomeando qual absorveria e em que proporção. |

O problema não é ser pequeno, é **não ser uma unidade de domínio** — um
micro frontend com uma tela é legítimo quando aquela tela é o domínio. O
tamanho não é condição: é o que desambigua qual dos dois é o pedaço.
Divisão equilibrada não é Nano Frontend, é um domínio mal repartido.

## [Access to different domains](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Access%20to%20different%20domains)
> Um MFE acessa diretamente APIs de vários domínios de negócio.

| | |
|---|---|
| **Entrada** | `Domain`, `ApiCall` |
| **Detecção** | Chamadas do micro frontend caindo em `min_domains` ou mais domínios. |
| **Saída** | Uma ocorrência por micro frontend, com os domínios consumidos e os endpoints de cada um. |

Distinto do `Mega Frontend`, e a diferença define o remédio: o Mega olha
o que o micro frontend **serve** — suas telas —, e a decomposição é a
saída; este olha de que ele **depende** — suas chamadas —, e a federação
de API é a saída.

**Depende do mapa de domínios.** Sem ele devolve vazio, porque qualquer
aproximação por prefixo de caminho seria arbitrária — dois proxies
observáveis existem e discordam entre si no repositório de referência:
base URL distinta daria zero detecções, prefixo de caminho daria duas.

---

# B — viável com os artefatos atuais

Nenhuma extração nova. Falta escrever a regra e, em alguns casos, decidir
um limiar.



## [Micro Frontends Greedy](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Micro%20Frontends%20Greedy)
> Explosão no número de MFEs.

| | |
|---|---|
| **Entrada** | `MicroFrontend` (contagem e tamanhos) |
| **Detecção** | Razão entre a quantidade de MFEs e o tamanho mediano de cada um. Acusa sistema com muitos MFEs pequenos. |
| **Saída** | Ocorrência única, sobre o sistema. Metadados: quantidade, mediana, distribuição de tamanhos. |

Sobrepõe-se a `Nano Frontend` — um olha a unidade, o outro o sistema.
Implementar as duas só se a distinção for defendida no texto.

## [Knot Micro Frontend](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Knot%20Micro%20Frontend)
> Três ou mais MFEs se comunicam diretamente por interfaces específicas.

| | |
|---|---|
| **Entrada** | `Communication`, `FragmentImport` |
| **Detecção** | Busca cliques de três ou mais nós — conjuntos em que todos se comunicam com todos. `networkx.find_cliques` resolve. |
| **Saída** | Uma ocorrência por clique. Metadados: os MFEs do nó e os canais ou fragmentos que os ligam. |

## [Bidirectional Data Flow](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Bidirectional%20Data%20Flow)
> Comunicação bidirecional entre a aplicação hospedeira e os MFEs remotos.

| | |
|---|---|
| **Entrada** | `MicroFrontend.role`, `Communication`, `FragmentImport`, `Navigation` |
| **Detecção** | O papel `shell` já identifica a hospedeira. Acusa par com aresta nos dois sentidos envolvendo o shell, em qualquer relação. |
| **Saída** | Uma ocorrência por par. Metadados: as relações em cada sentido. |

## [Chatty Micro Frontends](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Chatty%20Micro%20Frontends)
> Comunicação excessiva entre fragmentos, transmitindo evento a cada ação.

| | |
|---|---|
| **Entrada** | `Communication` |
| **Detecção** | Conta pontos de publicação por par de MFEs e acusa acima de um limiar. |
| **Saída** | Uma ocorrência por par. Metadados: canais, contagem de pontos de publicação. |

**Ressalva de natureza.** O catálogo descreve **frequência de execução**;
a análise estática vê **pontos no código**. Um `publish` dentro de um
laço conta um. É proxy fraco, e a regra não deve ser publicada sem essa
ressalva junto — senão promete medir algo que não mede.

## [Spaghetti Architecture](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Spaghetti%20Architecture)
> MFEs estruturados de forma desorganizada, com dependências emaranhadas.

| | |
|---|---|
| **Entrada** | todas as arestas |
| **Detecção** | Métricas de grafo: densidade, componentes fortemente conexos, ausência de estrutura em camadas. |
| **Saída** | Ocorrência única, sobre o sistema. Metadados: as métricas calculadas. |

O conceito é difuso. A regra vale o que a operacionalização escolhida
valer, e essa escolha precisa ser justificada no texto.


---

# C — precisa de extração nova

Ordenados por esforço crescente.

## [No CI&CD](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/No%20CI%26CD)
> Falta pipeline automatizado de integração e entrega.

| | |
|---|---|
| **Extração nova** | Presença de `.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`, `azure-pipelines.yml` por MFE |
| **Entrada** | a extração acima |
| **Detecção** | Ausência de qualquer um dos arquivos, por MFE e no repositório. |
| **Saída** | Ocorrência por MFE sem pipeline, ou única se nenhum tiver. |

Não é análise de código, é inspeção de repositório. O `SourceTree` já
percorre a árvore.

## [No Versioning](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/No%20Versioning)
> Os MFEs não são versionados.

| | |
|---|---|
| **Extração nova** | Campo `version` do `package.json`; presença de tags no git |
| **Entrada** | a extração acima |
| **Detecção** | Acusa MFE sem `version`, ou com versão fixa que nunca muda no histórico. |
| **Saída** | Uma ocorrência por MFE. |

## [Framework Frenzy](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Framework%20Frenzy) · [Golden Hammer](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Golden%20Hammer)
> Vários frameworks sem necessidade real · todos com a mesma tecnologia,
> mesmo quando não serve.

| | |
|---|---|
| **Extração nova** | Dependências declaradas no `package.json` de cada MFE, classificadas por família: react, vue, angular, svelte |
| **Entrada** | a extração acima |
| **Detecção** | `Framework Frenzy`: mais de N famílias no sistema. `Golden Hammer`: uma só, em todos. |
| **Saída** | Ocorrência única em cada caso. Metadados: a família de cada MFE. |

São o mesmo dado lido em direções opostas. **Golden Hammer é o mais
delicado do catálogo**: homogeneidade é problema só quando alguma unidade
precisava de outra tecnologia — e isso o código não diz. A detecção
identifica a homogeneidade, não a inadequação.

## [Dependency hell](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Dependency%20hell)
> MFEs compartilham bibliotecas externas sem gestão consistente de versão.

| | |
|---|---|
| **Extração nova** | Dependências e faixas de versão por MFE |
| **Entrada** | a extração acima |
| **Detecção** | Mesma biblioteca com faixas incompatíveis entre MFEs. |
| **Saída** | Uma ocorrência por biblioteca divergente. Metadados: as faixas e quem declara cada uma. |

**Uma extração de manifesto resolve quatro regras** — esta,
`Framework Frenzy`, `Golden Hammer` e `No Versioning`. É o melhor retorno
por esforço de toda a faixa C, e abre a categoria *Development*, hoje sem
nenhuma cobertura.

## [Avoiding observability](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Avoiding%20observability)
> Nenhuma observabilidade implementada.

| | |
|---|---|
| **Extração nova** | Imports de bibliotecas de observabilidade — Sentry, Datadog, OpenTelemetry, LogRocket — por MFE |
| **Entrada** | a extração acima |
| **Detecção** | Ausência de sinal em um ou em todos os MFEs. |
| **Saída** | Uma ocorrência por MFE sem sinal. |

Mesma técnica do catálogo de clientes HTTP: reconhecimento pelo
especificador do import.

Regra de **ausência**, o que é mais frágil que presença: não achar pode
significar instrumentação num pacote compartilhado. A saída deve dizer
"nenhum sinal encontrado", não "não existe".

## [Lack of Skeleton](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Lack%20of%20Skeleton)
> Não há esqueleto ou boilerplate padrão para criar novos MFEs.

| | |
|---|---|
| **Extração nova** | Estrutura de diretórios e arquivos de configuração de cada MFE |
| **Entrada** | a extração acima |
| **Detecção** | Similaridade estrutural entre os MFEs. Projetos gerados do mesmo esqueleto se parecem. |
| **Saída** | Ocorrência única. Metadados: a matriz de similaridade. |

Operacionalização delicada: baixa similaridade pode significar ausência
de esqueleto ou divergência legítima ao longo do tempo.

## [Dependent deployment](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Dependent%20deployment)
> MFEs tão acoplados que a implantação exige coordenação entre times.

| | |
|---|---|
| **Extração nova** | Sinais de release: versões fixadas entre MFEs, pipeline que publica vários juntos |
| **Entrada** | acoplamento já existente + a extração acima |
| **Detecção** | Acoplamento forte entre MFEs somado a sinal de release conjunto. |
| **Saída** | Uma ocorrência por grupo que precisa ser implantado junto. |

Sem a extração de release, dá para tratar como regra **composta** sobre
as detecções existentes — mas aí precisa ser nomeada como risco inferido,
não como fato observado.

## [Partial UI Migration](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Partial%20UI%20Migration)
> Extrair parte da UI para um MFE e reembuti-la no monólito legado.

| | |
|---|---|
| **Extração nova** | Identificação do monólito e da direção do embutimento |
| **Entrada** | a extração acima + `FragmentImport` |
| **Detecção** | MFE cujo fragmento é instanciado de volta dentro do legado. |
| **Saída** | Uma ocorrência por fragmento reembutido. |

Reconhecer uma aplicação **como legada** exige sinal que o código não dá
sozinho. Provavelmente precisa de declaração do usuário.

## [Unmediated Legacy Integration](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Unmediated%20Legacy%20Integration)
> Integrar sistema legado sem isolamento adequado.

Mesma dificuldade da anterior, agravada: exige identificar o legado **e**
avaliar a qualidade do isolamento. É a mais distante da faixa C.

## [Distributed Data Inconsistency](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Distributed%20Data%20Inconsistency)
> Dados replicados entre MFEs sem propagação de mudança.

| | |
|---|---|
| **Extração nova** | Modelos de dado definidos em cada MFE — formas de tipo ou de objeto |
| **Entrada** | a extração acima |
| **Detecção** | Modelos equivalentes definidos em mais de um MFE. |
| **Saída** | Uma ocorrência por modelo duplicado. |

Análise bem mais pesada que tudo que existe hoje, e com alta taxa de
falso positivo — dois MFEs podem legitimamente ter tipos parecidos.
**Eu deixaria fora do escopo.**

---

# D — fora do alcance

Não são propriedades do código. Nenhuma análise estática de fonte as
determina, e aproximá-las produziria número sem significado.

## [Common Ownership](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Common%20Ownership)
> Um único time gerencia todos os MFEs.

Estrutura organizacional. Existe aproximação possível — `CODEOWNERS` e
autoria no histórico do git —, mas isso é metadado de repositório, não
código, e mede **quem commitou**, não quem é dono.

Se entrar, seria extensão de escopo declarada: análise de repositório,
não de código.

## [Dismissing human factors](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Dismissing%20human%20factors)
> Times perseguem metas técnicas sem considerar bem-estar e moral.

Não detectável por nenhum meio automático.

## [Micro Frontend as the goal](https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Micro%20Frontend%20as%20the%20goal)
> Adotar a arquitetura MFE em contexto inadequado.

Exige julgar se o contexto justificava a decisão — informação que não
está no artefato. `Nano Frontend` e `Micro Frontends Greedy` capturam
sintomas correlatos, mas não a causa.

---

# Resumo para o escopo

**Cobertura atual:** 8 de 27. A categoria Intra-frontend está quase
fechada: falta `Micro Frontends Greedy`, que usa o mesmo mapa de domínios
das duas já implementadas.

**Alcance sem extração nova:** 13 de 27 — quase metade do catálogo.

**Melhor retorno por esforço:** a extração de manifesto — dependências e
versões por MFE — habilita quatro regras de uma vez e abre a categoria
*Development*, hoje sem cobertura.

**Menor esforço restante:** `Micro Frontends Greedy` não precisa de nada
novo. É a leitura no nível do sistema do mesmo cruzamento que
`nano-frontend` faz por unidade: mais micro frontends que domínios.

**Teto realista:** 24 de 27. Três são sobre pessoas e processo, e
declarar isso explicitamente é resultado: delimita o que análise estática
de código pode afirmar sobre arquitetura.

| categoria | total | A | B | C | D |
|---|---|---|---|---|---|
| Inter-frontend | 15 | 6 | 4 | 5 | 0 |
| Intra-frontend | 3 | 2 | 1 | 0 | 0 |
| Operations | 4 | 0 | 0 | 4 | 0 |
| Development | 5 | 0 | 0 | 2 | 3 |

## Três regras que exigem declaração metodológica

Estas medem conceitos que **não estão no artefato**. Implementá-las é
possível; publicá-las sem declarar a operacionalização, não.

| regra | o que o catálogo descreve | o que se consegue observar |
|---|---|---|
| `Access to different domains` | domínio de negócio | prefixo de caminho ou base URL |
| `Chatty Micro Frontends` | frequência de execução | pontos de publicação no código |
| `Golden Hammer` | tecnologia inadequada à necessidade | homogeneidade tecnológica |

Em todas, a detecção identifica o sintoma observável, não a causa
descrita. A distância entre os dois é ameaça à validade, e vale enunciá-la.
