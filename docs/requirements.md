# damfe — requisitos

Histórias de usuário que documentam as funcionalidades da ferramenta. São 36, das quais 28 implementadas ou parciais.

Cada história tem critérios de aceite verificáveis. O estado indica se a
funcionalidade existe hoje:

- **Implementado** — existe e foi exercitado
- **Parcial** — existe com limitação registrada
- **Pendente** — identificado, não construído

Papéis:

| papel | quem é |
|---|---|
| **analista** | quem investiga a arquitetura de um sistema micro frontend |
| **desenvolvedor** | quem trabalha num dos micro frontends |
| **pesquisador** | quem usa a ferramenta como instrumento de estudo |
| **mantenedor** | quem estende a própria ferramenta |

---

## Épico 1 — Reconstrução arquitetural

Extrair do código-fonte os artefatos que descrevem a arquitetura.

### US-01 · Descobrir os micro frontends do sistema

> Como **analista**, quero obter a lista de micro frontends de um
> repositório, para saber quais unidades independentes existem sem
> depender de documentação.

**Critérios de aceite**
- A descoberta parte das chamadas de `registerApplication`, que é o
  contrato de registro do single-spa.
- Micro frontends sem pacote próprio são encontrados.
- As duas formas da API são aceitas: objeto (`{name, app, activeWhen}`) e
  posicional (`(name, loadingFn, activeWhen)`).
- Um micro frontend registrado cujo entrypoint não seja resolvível ainda
  aparece no resultado, com os campos que puderam ser determinados.

**Estado:** Implementado

---

### US-02 · Distinguir o orquestrador dos demais

> Como **analista**, quero saber qual é o shell, para não confundir a
> aplicação que orquestra com as que ela orquestra.

**Critérios de aceite**
- O micro frontend que reside no pacote que declara os registros é
  marcado com papel distinto.
- O papel fica disponível nos artefatos para uso por regras e
  visualizações.

**Estado:** Parcial — a heurística é a coabitação de pacote. Dois
micro frontends registrados no mesmo pacote tornam a marcação ambígua.

---

### US-03 · Inventariar telas e rotas

> Como **analista**, quero as telas de cada micro frontend com suas
> rotas, para saber o que cada um entrega ao usuário.

**Critérios de aceite**
- As telas vêm das `<Route>` declaradas pelo componente raiz.
- A rota é resolvida quando expressa por constante
  (`path={checkoutRoutes.CART}` → `/checkout/cart`), inclusive com um
  nível de indireção entre constantes.
- Quando a rota não resolve, a expressão original é preservada.

**Estado:** Implementado

---

### US-04 · Inventariar os fragmentos expostos

> Como **desenvolvedor**, quero saber o que meu micro frontend expõe
> publicamente, para conhecer a superfície que os outros podem consumir.

**Critérios de aceite**
- Fragmentos são os exports do entrypoint que não pertencem ao contrato
  de lifecycle (`bootstrap`, `mount`, `unmount`, `update`).
- Cada fragmento aponta o arquivo que o define.

**Estado:** Implementado

---

### US-05 · Descobrir consumo de fragmento entre micro frontends

> Como **analista**, quero saber quem usa componente de quem, para medir
> o acoplamento de build entre as partes.

**Critérios de aceite**
- Só conta import cujo nome importado pertença ao catálogo de fragmentos
  do módulo de origem — bibliotecas compartilhadas não entram.
- Alias no import é resolvido.
- Cada consumo registra onde foi importado e onde foi instanciado em JSX,
  com as props passadas.
- Import sem instanciação correspondente é registrado como tal.

**Estado:** Implementado

---

### US-06 · Descobrir navegação entre micro frontends

> Como **analista**, quero saber quais micro frontends levam o usuário a
> quais outros, para enxergar o acoplamento de fluxo, que é invisível no
> grafo de dependências de código.

**Critérios de aceite**
- A detecção não depende de conhecer o roteador nem a biblioteca de
  navegação do projeto.
- O dono de cada rota é determinado pelo `activeWhen` declarado no
  registro, com casamento por prefixo e fronteira de segmento.
- Prefixo mais longo vence, para que o catch-all do shell não absorva
  todas as rotas.
- `activeWhen: ["/"]` casa apenas a URL exata `/`, e não todo caminho do
  sistema.
- Destinos expressos por literal, constante, template ou
  `.replace(":param", …)` são resolvidos; o grau de certeza (`exact` ou
  `prefix`) acompanha cada resultado.
- Navegação interna ao próprio micro frontend não é reportada.

**Estado:** Implementado

---

### US-07 · Declarar o mecanismo de comunicação

> Como **analista**, quero declarar uma vez como os micro frontends
> trocam mensagens, para que a extração seja determinística mesmo sem
> haver um padrão no ecossistema.

**Critérios de aceite**
- Um comando gera um arquivo modelo comentado.
- A declaração fica em `.damfe/` na raiz do repositório analisado, e não
  junto dos artefatos, por ser entrada da análise e não saída.
- A declaração sobrevive à remoção do diretório de saída.
- O formato descreve, para cada mecanismo, o módulo, o nome exportado e a
  posição do canal nos argumentos, dos dois lados.

**Estado:** Implementado

---

### US-08 · Descobrir comunicação entre micro frontends

> Como **analista**, quero saber quem publica e quem consome cada canal,
> para conhecer o acoplamento por mensagem.

**Critérios de aceite**
- Só os mecanismos declarados são procurados; a ferramenta não adivinha.
- As funções são reconhecidas pelo import, de modo que alias não escape.
- O canal é resolvido quando literal ou constante.
- Produtor e consumidor são pareados pelo valor do canal.
- Sem declaração, o resultado é vazio e o comando informa que o setup não
  foi feito — estado distinto de "não há comunicação".

**Estado:** Implementado

---

### US-09 · Executar cada extração isoladamente

> Como **analista**, quero rodar só a extração que me interessa, para
> inspecionar um aspecto sem pagar o custo do resto.

**Critérios de aceite**
- Existe um comando por tipo de artefato.
- A varredura do repositório é reaproveitada quando os passos são
  encadeados, sem reprocessar os mesmos arquivos.

**Estado:** Implementado

---

### US-10 · Persistir os artefatos

> Como **pesquisador**, quero os artefatos em arquivo, para versioná-los
> e comparar a arquitetura entre dois momentos do projeto.

**Critérios de aceite**
- Uma coleção por arquivo, em JSON legível.
- O conteúdo é estável entre execuções sobre o mesmo código, de modo que
  o diff entre versões reflita mudança real na arquitetura.
- Os artefatos podem ser relidos e alimentar as demais etapas sem nova
  leitura do código-fonte.

**Estado:** Implementado

---

### US-11 · Reconhecer a tecnologia automaticamente

> Como **analista**, quero que a ferramenta identifique sozinha a
> tecnologia do repositório, para não precisar informá-la.

**Critérios de aceite**
- A detecção usa sinais independentes: dependência declarada no manifesto
  e presença da chamada de registro no código.
- É possível forçar um extrator específico.
- Quando nenhum extrator reconhece o repositório, a ferramenta diz isso
  em vez de produzir resultado vazio.

**Estado:** Implementado

---

### US-12 · Restringir a análise a uma organização

> Como **analista**, quero considerar apenas os micro frontends de uma
> organização, para excluir registros de terceiros num monorepo.

**Critérios de aceite**
- Um prefixo opcional filtra os micro frontends considerados.
- Sem prefixo, todos os registrados entram.

**Estado:** Implementado

---

## Épico 2 — Detecção de anti-padrões

Avaliar os artefatos em busca de desvios arquiteturais.

### US-13 · Aplicar as regras sobre os artefatos

> Como **analista**, quero rodar as regras sobre os artefatos extraídos,
> para descobrir problemas sem reler o código.

**Critérios de aceite**
- A detecção opera apenas sobre o modelo de artefatos, sem acesso ao
  código-fonte.
- É possível aplicar todas as regras ou selecionar por nome.
- As ocorrências são ordenadas por gravidade.
- Cada ocorrência aponta os elementos envolvidos e, quando aplicável, os
  locais no código.
- Ausência de regras registradas é informada, e não confundida com
  ausência de problemas.

**Estado:** Implementado

---

### US-14 · Detectar ciclo de dependência

> Como **analista**, quero saber se micro frontends dependem uns dos
> outros em ciclo, porque isso quebra a premissa de implantação
> independente.

**Critérios de aceite**
- As três relações são avaliadas separadamente, não num grafo único.
- A gravidade acompanha o significado da relação: importação de fragmento
  é acoplamento de build; comunicação é acoplamento de contrato;
  navegação em ciclo costuma ser fluxo legítimo.
- A mensagem apresenta o ciclo na ordem em que se fecha.
- A enumeração tem teto, para que um grafo denso não trave a execução.

**Estado:** Implementado

---

### US-15 · Detectar tela que concentra fragmentos de vários micro frontends

> Como **analista**, quero identificar telas que agregam fragmentos de
> muitos micro frontends, porque elas viram ponto de convergência de
> falha e de mudança.

**Critérios de aceite**
- O sinal é a quantidade de provedores distintos, não a de fragmentos:
  vários fragmentos do mesmo provedor são reúso.
- O limiar é configurável no registro da regra.

**Estado:** Parcial — a ligação entre fragmento e tela é feita pelo
arquivo. Fragmento instanciado em componente auxiliar que a tela renderiza
não é atribuído a ela.

---

### US-16 · Detectar micro frontend conectado a quase todos

> Como **analista**, quero identificar um micro frontend que toca quase
> todo o sistema, porque ele deixou de ser uma parte independente.

**Critérios de aceite**
- A conexão é contada sem direção, unindo as três relações.
- A proporção de cada sentido é registrada, porque depender de todos e
  ser dependido por todos são problemas distintos.
- O orquestrador é excluído do cálculo, por alcançar todos por definição.
- Sistemas abaixo de um tamanho mínimo não são avaliados, porque neles
  estar conectado a todos é o normal.
- Proporção e tamanho mínimo são configuráveis.

**Estado:** Implementado

---

### US-17 · Persistir as detecções

> Como **pesquisador**, quero as detecções em arquivo, para acompanhar a
> evolução dos desvios ao longo do tempo.

**Critérios de aceite**
- As ocorrências são gravadas em JSON com regra, gravidade, mensagem,
  elementos envolvidos, locais e metadados.
- O arquivo pode ser relido pela etapa de visualização.

**Estado:** Implementado

---

## Épico 3 — Visualização

### US-18 · Obter um relatório visual completo

> Como **analista**, quero um relatório visual da arquitetura e dos
> desvios, para comunicar o resultado a quem não vai ler JSON.

**Critérios de aceite**
- Arquivo único, sem dependência de rede: abre offline e pode ser
  arquivado junto do texto que o cita.
- O desenho é gerado na própria ferramenta, e não no navegador, de modo
  que os mesmos artefatos produzam sempre a mesma imagem.
- O grafo distingue visualmente as três relações.
- Arestas de ida e de volta entre o mesmo par são distinguíveis.
- O relatório apresenta as contagens, o grafo, as detecções com seus
  locais, e o detalhamento de cada micro frontend.

**Estado:** Implementado

---

### US-19 · Ver os desvios sobre o desenho da arquitetura

> Como **analista**, quero os elementos com detecção destacados no grafo,
> para que o desenho seja evidência do achado, e não ilustração.

**Critérios de aceite**
- Elementos citados em alguma detecção são destacados.
- O destaque é distinguível da marcação do orquestrador.

**Estado:** Implementado — cada regra declara em `metadata.edges` quais
pares compõem a ocorrência, e o desenho destaca nós e arestas.

---

### US-20 · Isolar uma relação no desenho

> Como **analista**, quero ver uma relação por vez, para comparar o grafo
> de código com o grafo de fluxo.

**Critérios de aceite**
- Cada relação pode ser ligada e desligada no relatório.
- O relatório permanece correto e legível sem execução de script.

**Estado:** Implementado

---

## Épico 4 — Extensibilidade

### US-21 · Acrescentar uma regra de anti-padrão

> Como **mantenedor**, quero escrever uma regra nova sem alterar o
> restante da ferramenta, para que o catálogo cresça sem risco de
> regressão.

**Critérios de aceite**
- Uma regra é uma classe que implementa a interface e um registro.
- A regra recebe o modelo de artefatos e não conhece a tecnologia que os
  originou, de modo que valha para qualquer uma.
- Nenhuma alteração é necessária em portas, casos de uso ou interface de
  linha de comando.

**Estado:** Implementado — exercitado por três regras.

---

### US-22 · Acrescentar um formato de visualização

> Como **mantenedor**, quero acrescentar formatos de saída sem alterar a
> lógica de análise.

**Critérios de aceite**
- Um formato é uma classe que implementa a interface e um registro.
- A seleção acontece por nome na linha de comando.

**Estado:** Implementado

---

### US-23 · Acrescentar suporte a outra tecnologia de micro frontend

> Como **mantenedor**, quero estender a ferramenta a outra tecnologia sem
> tocar nos módulos de detecção e visualização.

**Critérios de aceite**
- Um extrator é uma classe que implementa a interface e um registro.
- O extrator traduz o vocabulário da tecnologia para o modelo neutro.
- Os módulos de detecção e visualização permanecem inalterados.

**Estado:** Parcial — a estrutura existe e é respeitada, mas só um
extrator foi escrito. A neutralidade do modelo permanece hipótese até o
segundo.

---

## Backlog

Funcionalidades identificadas e não construídas.

### US-24 · Extrair o acesso ao estado global

> Como **analista**, quero saber que fatias do estado global cada micro
> frontend lê, porque dois que leem a mesma fatia dependem do mesmo
> formato de dado sem se conhecerem.

**Critérios de aceite**
- As bibliotecas de estado são reconhecidas pelo import — react-redux,
  zustand, jotai, recoil, mobx, pinia —, não por nome de variável.
- Um seletor que monta objeto conta cada fatia que percorre.
- Acesso em pacote compartilhado não é acoplamento entre micro
  frontends e fica de fora.
- Só a leitura é extraída: a escrita revela o nome da ação despachada,
  não a fatia alterada, e misturar as duas juntaria vocabulários
  distintos.

**Estado:** Implementado

---

### US-29 · Descobrir as chamadas a serviços externos

> Como **analista**, quero saber que serviços cada micro frontend
> consome, para enxergar o acoplamento por backend — invisível nos
> grafos de código e de fluxo.

**Critérios de aceite**
- `fetch` e `XMLHttpRequest` são reconhecidos sem configuração, por
  serem API da plataforma web e não de framework.
- Clientes conhecidos são identificados pelo especificador do import,
  incluindo instâncias criadas por fábrica como `axios.create()`.
- O caminho é resolvido pelo mesmo avaliador parcial das rotas, com o
  grau de certeza registrado.
- Cada chamada registra as telas e os fragmentos que a alcançam,
  seguindo os imports internos ao micro frontend.
- Lista de alcance vazia é informação: a chamada está em código que
  nenhuma tela alcança.

**Estado:** Implementado

---

### US-30 · Medir o tamanho de cada micro frontend

> Como **pesquisador**, quero o tamanho de cada unidade, para
> corroborar os achados de granularidade e comparar sistemas.

**Critérios de aceite**
- A contagem acontece durante a varredura que já existe, sem segunda
  leitura do disco.
- Linha de comentário é identificada pela árvore sintática, não por
  prefixo de texto: `//` dentro de uma string não conta.
- Linha com código e comentário ao final continua sendo linha de
  código.

**Estado:** Implementado

---

### US-31 · Declarar os domínios de negócio

> Como **analista**, quero declarar os domínios do sistema, porque
> domínio de negócio não está no código e nenhuma análise estática o
> determina.

**Critérios de aceite**
- A declaração fica em `.damfe/domains.yml`, versionada com o projeto.
- Rotas e endpoints são campos separados, por serem vocabulários
  distintos.
- Subdomínio é registro, não divisão: suas rotas e endpoints entram no
  domínio que o contém, e as regras operam no nível de topo.
- O casamento é por prefixo com fronteira de segmento, e `/` casa apenas
  o caminho exato — senão um domínio declarado com `/` engoliria o
  sistema.
- Os domínios resolvidos são persistidos como artefato, com os membros e
  os micro frontends que os servem.

**Estado:** Implementado

---

### US-32 · Detectar desalinhamento entre domínio e micro frontend

> Como **analista**, quero saber quando a divisão em micro frontends não
> corresponde à divisão em domínios, porque é isso que caracteriza
> granularidade errada.

**Critérios de aceite**
- Micro frontend servindo mais de um domínio é acusado, nomeando **quais
  telas destoam e a que domínio pertencem**.
- Micro frontend cobrindo parte de um domínio que outro serve mais é
  acusado, nomeando qual o absorveria.
- O tamanho não é condição: ele desambigua qual dos dois é o pedaço, e
  corrobora na evidência.
- Sem mapa declarado, as regras caem no tamanho relativo à mediana do
  sistema e informam o critério usado.
- Micro frontend cujas telas não caem em domínio nenhum é indeterminado,
  e a regra se abstém.

**Estado:** Implementado

---

### US-33 · Sumarizar o sistema para autoria assistida

> Como **analista**, quero uma sumarização compacta do sistema, para
> servir de entrada a um assistente que proponha os domínios.

**Critérios de aceite**
- A saída reúne, por micro frontend, telas com rotas, fragmentos
  expostos e compostos, serviços chamados e estado lido.
- Campos irrelevantes à pergunta — caminho de arquivo, número de linha,
  props — ficam de fora.
- A sumarização é gerada pela própria ferramenta, deterministicamente.

**Estado:** Implementado

---

### US-34 · Guardar o acesso a um modelo de linguagem

> Como **analista**, quero guardar uma credencial uma vez, para os passos
> de autoria assistida, sem informá-la a cada execução.

**Critérios de aceite**
- A credencial fica no diretório do usuário, **nunca** em `.damfe/`, que
  é versionado com o projeto analisado.
- O arquivo é criado com permissão de leitura só para o dono, sem janela
  em que outros possam lê-lo.
- Variável de ambiente tem precedência sobre o arquivo.
- A credencial nunca é exibida por inteiro.
- Nenhum comando de análise usa essa configuração.

**Estado:** Implementado

---

### US-25 · Relatar o que não pôde ser resolvido

> Como **pesquisador**, quero saber o que a análise não conseguiu
> determinar, para poder afirmar a cobertura do método em vez de
> apresentá-lo como completo.

**Estado:** Pendente — sem isso, a recuperação do método não é
mensurável.

---

### US-26 · Registrar a contenção entre componentes

> Como **analista**, quero que fragmentos instanciados dentro de
> componentes auxiliares sejam atribuídos à tela que os contém, para que
> a concentração de dependências não seja subestimada.

**Estado:** Parcial — o alcance entre arquivos já existe e é usado para
atribuir chamadas de serviço às telas (US-29). Falta aplicá-lo à
instanciação de fragmento, que ainda liga pelo arquivo — é o que bloqueia
a correção da US-15.

---

### US-27 · Gerar a declaração de comunicação a partir de descrição

> Como **analista**, quero descrever em texto corrido como o sistema se
> comunica e obter a declaração pronta, para não precisar aprender o
> formato.

**Critérios de aceite previstos**
- A proposta é validada contra o esquema e verificada contra o
  repositório antes de ser gravada.
- A não-determinância fica confinada ao passo de setup, cujo resultado é
  revisado e versionado; a análise permanece reproduzível.

**Estado:** Pendente — existe uma instrução para agente, sem integração
na ferramenta.

---

### US-28 · Suíte de testes automatizados

> Como **mantenedor**, quero testes que cubram extração, regras e
> persistência, para poder afirmar que a reconstrução é reproduzível e
> alterar a ferramenta sem regressão silenciosa.

**Estado:** Pendente — a arquitetura foi construída para permitir isso
(portas injetadas, casos de uso sem efeito colateral), e a possibilidade
está sem uso.

---

### US-35 · Avisar quando os artefatos estiverem defasados

> Como **analista**, quero ser avisado quando uma declaração mudou depois
> da última reconstrução, porque hoje a detecção usa a resolução antiga
> sem sinalizar nada.

**Estado:** Pendente — editar `domains.yml` ou `communication.yml` e
rodar só o `detect` produz resultado plausível e desatualizado.

---

### US-36 · Extrair comunicação via `customProps`

> Como **analista**, quero conhecer o estado e as ações que o
> orquestrador injeta em cada micro frontend, porque é um canal
> padronizado pela tecnologia e não exige declaração.

**Estado:** Pendente — é um dos mecanismos usados pelo repositório de
referência, hoje não extraído.
