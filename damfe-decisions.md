# Decisões de projeto do DAMFE

Documento vivo. Uma entrada por decisão, com a razão. Decisão
revertida fica registrada como revertida, não some.

Última atualização: 19/09/2026.

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

**Um arquivo de artefato por coleção.** Sem índice ou manifesto: não
havia consumidor para ele.

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
sem aviso. Se virar problema na prática, US-25 trata.

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

## Pendências conhecidas

| | |
|---|---|
| US-25 | relatar cobertura e o que não foi resolvido |
| US-26 | contenção de componente para fragmento → tela |
| US-27 | spec de comunicação gerada por LLM, integrada |
| US-28 | suíte de testes automatizados |
| US-35 | avisar quando os artefatos estão obsoletos |
| US-36 | extrair `customProps` |
| — | `hub-like-dependency` conta aresta simétrica em dobro |
| — | apresentação conta estado global duas vezes (aresta e acesso) |
| — | reconstrutor para Module Federation: 63% da população amostrada |
