# Prompt — estender o damfe para o seu projeto

Este arquivo é um prompt. Entregue-o a qualquer assistente de código —
não depende de ferramenta específica.

**Assistente com acesso ao repositório** (Claude Code, Cursor, Copilot,
aider, Continue): abra o repositório, cole este arquivo e diga o que
você precisa.

**Assistente sem acesso a arquivos** (ChatGPT, Gemini, modelo local por
chat): cole este arquivo e, quando for pedido, cole também o conteúdo
dos arquivos listados.

---

## Sobre a ferramenta

O damfe faz análise estática de arquiteturas micro frontend. Ele separa
**o que é extraído** de **como se extrai**: o modelo de domínio e os
módulos de detecção e visualização são neutros de tecnologia, e quem
conhece uma tecnologia específica é um único adaptador, o reconstrutor.

Três coisas podem precisar ser escritas para um projeto:

| o que | quando | ciclo | resultado |
|---|---|---|---|
| **declaração de comunicação** | o projeto tem barramento de eventos próprio | uma vez por projeto | um YAML |
| **mapa de domínios** | você quer analisar coesão e acesso a domínios | uma vez por projeto | um YAML |
| **reconstrutor** | a tecnologia do projeto ainda não é suportada | uma vez por tecnologia | código Python |

## Comece pela triagem

Antes de qualquer outra coisa, descubra qual das duas o usuário precisa.
Pergunte:

> Qual tecnologia de micro frontend o projeto usa? E os micro frontends
> trocam mensagens entre si de alguma forma — barramento de eventos,
> pub/sub, algo assim?

Pergunte também se ele quer analisar **domínios de negócio** — coesão
de cada micro frontend, ou acesso a domínios demais.

Com as respostas:

- **Tecnologia não suportada** → **Parte B** primeiro. Sem reconstrutor
  não há artefato, e sem artefato as outras partes não têm entrada.
- **Há comunicação própria** → **Parte A**.
- **Quer análise de domínio** → **Parte C**.

Não faça a Parte B por precaução. Escrever um reconstrutor quando já
existe um que funciona é trabalho jogado fora.

## Regras da entrevista

Valem para as duas partes.

Você conduz uma **entrevista**, não recebe uma especificação. O usuário
não sabe de antemão o que você precisa. Pergunte, espere a resposta,
pergunte de novo — até ter tudo. Só então produza qualquer coisa.

- **Uma ou duas perguntas por vez.** Um questionário de dez itens não é
  respondido; é abandonado.
- **Não avance com lacuna.** Se algo essencial não veio, pergunte de
  novo, reformulando. Nunca preencha por suposição.
- **Não peça o que você mesmo pode ver.** Com acesso ao repositório,
  abra o arquivo. Pergunte só o que o código não responde.
- **Peça código, não descrição.** Descrição produz resultado errado.
- **Repita o que entendeu** antes de escrever, em três ou quatro linhas,
  e peça confirmação. É mais barato corrigir ali que no resultado.

---

# Parte A — declarar a comunicação

O damfe extrai rotas e fragmentos sem configuração, porque a tecnologia
de micro frontend padroniza esses contratos. Comunicação não tem padrão:
cada projeto escolhe o seu — barramento de eventos, store compartilhado,
`postMessage`, biblioteca própria.

Por isso o mecanismo é **declarado uma vez**, num arquivo, e a extração
passa a ser determinística.

O resultado desta parte é `.damfe/communication.yml`, na raiz do
repositório analisado.

## O formato

```yaml
mechanisms:
  - name: eventos            # rótulo livre, aparece na saída
    kind: pubsub             # único tipo suportado hoje
    produce:
      module: "@org/utils"   # especificador do import, literal
      export: publishEvent   # nome EXPORTADO pelo módulo
      channel_argument: 0    # posição do canal nos argumentos, base 0
    consume:
      module: "@org/utils"
      export: subscribeToTopic
      channel_argument: 0
```

Vários mecanismos podem coexistir na lista.

### O significado exato de cada campo

**`module`** — o especificador exatamente como aparece no `import`. Se o
código faz `import { publishEvent } from "@org/utils"`, o valor é
`@org/utils`. Nunca o caminho do arquivo no disco.

**`export`** — o nome sob o qual o módulo exporta a função, não o nome
local de quem importa. Em `import { subscribeToTopic as listen }`, o
valor é `subscribeToTopic`. O damfe resolve o alias sozinho.

**`channel_argument`** — em qual posição está o nome do canal. Em
`publishEvent(topic, data)` é `0`; em `emit(payload, topic)` é `1`.

O `produce` e o `consume` são pareados **pelo valor do canal**. É o canal
que é o contrato entre as duas pontas, não a chamada.

## Como conduzir

### A1. Colha

O que você precisa ter antes de escrever o arquivo:

- [ ] **Um exemplo de publicação** — a linha de código que envia a
      mensagem.
- [ ] **Um exemplo de consumo** — a linha que a recebe. Os dois lados,
      senão não há como parear.
- [ ] **De onde essas funções vêm** — a linha de `import` de cada uma.
- [ ] **Onde elas são definidas** — o arquivo que as exporta.

Um exemplo de chamada costuma dar `export` e `channel_argument` de uma
vez. O `import` dá o `module`.

### A2. Confirme no código, não na descrição

Antes de escrever o YAML, verifique no repositório:

- Onde a função é **definida e exportada** — confirma o `export`.
- Como ela é **importada** por quem usa — confirma o `module`. Atenção:
  o pacote pode ser importado por um especificador diferente do nome da
  pasta.
- Uma chamada real — confirma o `channel_argument`.

Se a descrição do usuário divergir do código, **o código vence**. Diga a
ele o que você encontrou.

### A3. Pergunte só o que o código não responde

Não interrogue sobre o que dá para verificar. Pergunte quando:

- Existem vários mecanismos e não está claro quais declarar.
- A função é chamada com o canal em posições diferentes conforme o caso.
- O canal não é argumento, e sim parte do nome da função
  (`onCartUpdated()`) — isso o formato atual não cobre. Explique a
  limitação em vez de forçar um mapeamento errado.

### A4. Escreva e valide

Escreva o arquivo e peça ao usuário que rode:

```
damfe communications <repo>
```

Compare o resultado com o que ele descreveu.

**Zero comunicações quando o usuário afirmou que existem é sinal de erro
na declaração**, quase sempre um `module` que não bate com o
especificador real do import. Não encerre sem investigar isso: o comando
não acusa erro nenhum nesse caso, apenas devolve vazio.

Mostre a ele as arestas encontradas, não só o arquivo gerado.

## Limites que você deve declarar

Diga ao usuário quando o mecanismo dele não couber, em vez de aproximar:

- **Canal dinâmico** (`publish(algumaVariavel)`) não resolve
  estaticamente. Literais e constantes resolvem; o resto vira o texto da
  expressão, o que ainda pareia se as duas pontas usarem a mesma
  constante.
- **Canal no nome da função** não é suportado.
- **`window` e `postMessage` diretos**, sem passar por um módulo
  compartilhado, não têm `module` para ancorar.
- **Estado compartilhado injetado pelo orquestrador** não é pub/sub e
  não se declara aqui.

## Exemplo completo

O usuário diz:

> A gente publica evento com `publishEvent` e escuta com
> `subscribeToTopic`, os dois vêm do nosso pacote de utils. O primeiro
> argumento é sempre o tópico.

Você verifica no repositório, encontra `utils/src/events/publish.js`
exportando `publishEvent`, e os consumidores importando de `@org/utils`.
Escreve:

```yaml
mechanisms:
  - name: eventos
    kind: pubsub
    produce:
      module: "@org/utils"
      export: publishEvent
      channel_argument: 0
    consume:
      module: "@org/utils"
      export: subscribeToTopic
      channel_argument: 0
```

Pede para rodar `damfe communications`, e reporta:

> 2 comunicações: `@org/app-a → @org/app-b` nos canais `cart.updated` e
> `checkout:started`.

---

# Parte B — escrever um reconstrutor

Só faça esta parte se a tecnologia do projeto **não** for reconhecida
pelo damfe. O trabalho termina quando o usuário roda
`damfe reconstruct` no repositório dele e obtém artefatos corretos — não
quando o código importa sem erro.

## Contexto necessário

Se você tem acesso ao repositório, leia antes de escrever:

```
src/damfe/application/ports/driven.py                  o contrato
src/damfe/domain/model.py                              as entidades
src/damfe/domain/communication.py
src/damfe/adapters/driven/reconstruction/ast/          os utilitários
src/damfe/adapters/driven/reconstruction/singlespa/    exemplo completo
src/damfe/composition.py                               onde registrar
```

Se não tem, peça ao usuário que cole esses arquivos.

## O contrato

```python
class Reconstructor(ABC):
    name: str          # identificador no CLI, ex.: "module-federation"
    description: str

    def detect(self, repository: Path) -> bool: ...
    def microfrontends(self, repository: Path) -> list[MicroFrontend]: ...
    def fragment_imports(self, repository, microfrontends) -> list[FragmentImport]: ...
    def navigations(self, repository, microfrontends) -> list[Navigation]: ...
    def communications(self, repository, microfrontends, spec) -> list[Communication]: ...
    def api_calls(self, repository, microfrontends) -> list[ApiCall]: ...
```

As entidades do domínio, em resumo:

```python
MicroFrontend(id, directory, entrypoint, routes, role, fragments,
              screens, size, metadata)
Screen(component, microfrontend, route, route_expression, file, line)
Fragment(name, microfrontend, file, line)

FragmentImport(consumer, provider, fragment, local_name,
               imported_at, renders)
Navigation(source, target, expression, resolved_url, match, at)
Communication(source, target, mechanism, channel,
              produced_at, consumed_at)
ApiCall(microfrontend, method, path, match, client, at)

SourceLocation(file, line, code)
```

`match` vale `"exact"` quando o valor foi determinado por inteiro, ou
`"prefix"` quando só o começo dele é estático.

Não invente campo nem altere entidade. Se faltar lugar para guardar
algo, use `MicroFrontend.metadata`, que é um dicionário livre. Mudar o
modelo afeta as regras de detecção e a visualização, e é decisão do
usuário.

## Reaproveite o motor

Estes utilitários já existem em
`src/damfe/adapters/driven/reconstruction/ast/` e são neutros de
tecnologia. **Usá-los é requisito, não sugestão** — reimplementar
travessia de AST cria um segundo jeito de fazer a mesma coisa, pior e
divergente.

| utilitário | serve para |
|---|---|
| `AstReader` | `parse(file)` → `(root, source)`; `walk`; `find_all(tipo)`; `text(node, source)`; `strip_quotes` |
| `SourceTree` | percorre arquivos-fonte podando `node_modules`; `manifests()` acha os `package.json` |
| `ImportTable` | `records(root, source)` devolve nome local, nome importado e módulo — resolve alias sozinho |
| `ModuleResolver` | `"./x"` → arquivo real, com extensão implícita e `/index` |
| `RouteConstantTable` | propaga constantes: `routes.CART` → `/checkout/cart`, inclusive por indireção |

Em `.../reconstruction/singlespa/` há mais dois. Copie para o seu pacote
se servirem, ou promova para `ast/` se forem gerais:

- `ExpressionEvaluator` — avalia parcialmente uma expressão: literal,
  constante, template, concatenação, `.replace(":id", …)`.
- `Ownership` — dono de um arquivo pelo diretório; dono de uma rota por
  prefixo mais longo, com fronteira de segmento.

**Nunca chame `parser.parse()` diretamente.** Use `AstReader`, que
mantém as árvores vivas. Um `Node` do tree-sitter aponta para memória da
`Tree`; se ela é coletada, o processo morre por falha de segmentação sem
lançar exceção.

## O exemplo resolvido

`.../reconstruction/singlespa/` é um reconstrutor completo:

| arquivo | papel |
|---|---|
| `reconstructor.py` | implementa a porta e memoriza a varredura |
| `context.py` | varre o repositório UMA vez, colhendo junto constantes e declarações |
| `microfrontends.py` | monta as unidades, com fragmentos e telas |
| `fragment_imports.py` | cruza imports com o catálogo de fragmentos |
| `navigations.py` | destino → dono da rota |
| `api_calls.py` | `fetch`, `XMLHttpRequest` e clientes HTTP conhecidos |
| `communications.py` | mecanismo declarado pelo usuário |

Repare no que **não** é específico do single-spa: o cruzamento com o
catálogo de fragmentos, a resolução de destino de navegação e a extração
de chamadas externas. Se a tecnologia nova tiver os mesmos conceitos,
essa lógica se repete quase inteira — o que muda é a descoberta.

## Como conduzir

### B1. Peça código, não descrição

O usuário vai tender a descrever com palavras. Descrição gera código
errado. O que você precisa ter em mãos antes de escrever qualquer linha:

- [ ] **Onde os micro frontends são declarados.** O arquivo inteiro, não
      um trecho. Se forem vários, um exemplo de cada forma.
- [ ] **Como um módulo é exposto** por um micro frontend **e como é
      consumido** por outro. Os dois lados, senão você não consegue
      cruzar um com o outro.
- [ ] **Como as rotas são declaradas**, e se há algo dizendo qual micro
      frontend é dono de qual caminho.
- [ ] **Se existe mecanismo de comunicação** próprio — aqui basta um
      sim ou não, veja abaixo.
- [ ] **Como o repositório é organizado** — monorepo, repositórios
      separados, onde fica o orquestrador se houver.

Marque os itens conforme forem chegando. Enquanto houver item em aberto,
continue perguntando.

### B2. A comunicação é a Parte A

Se o usuário disser que há mecanismo de comunicação próprio, **não
tente extraí-lo no reconstrutor**. Comunicação não tem contrato padrão
em nenhuma tecnologia: ela é declarada num arquivo, pelo usuário, uma
vez por projeto.

O método `communications()` da porta recebe essa declaração pronta, como
parâmetro `spec`. Na maior parte dos casos sua implementação será igual
à do single-spa — procurar as funções que a declaração nomeia, resolver
o canal e parear as duas pontas. Copie de
`.../reconstruction/singlespa/communications.py`; ela quase não depende
da tecnologia.

Terminado o reconstrutor, volte à **Parte A** deste prompt para produzir
o arquivo. São tarefas de ciclos diferentes: o reconstrutor se escreve
uma vez por tecnologia, a declaração uma vez por projeto.

### B3. Encontre a âncora

A pergunta central é: **qual é o contrato obrigatório da tecnologia?**

No single-spa é a chamada `registerApplication` — toda aplicação passa
por ela. É isso que permite descobrir aplicações que não têm pacote
próprio, e o `activeWhen` declarado ali é o que diz de quem é cada rota.

Procure o equivalente. Se não existir contrato obrigatório para algum
aspecto, **diga isso ao usuário** em vez de inventar heurística.
Limitação declarada é resultado melhor que suposição silenciosa.

### B4. Escreva

Crie `src/damfe/adapters/driven/reconstruction/<tecnologia>/` seguindo a
estrutura do exemplo. Deixe o `__init__.py` do pacote **vazio**, só com
uma docstring — importar o reconstrutor ali cria ciclo com os módulos
internos.

Registre no `bootstrap()` de `src/damfe/composition.py`:

```python
reconstruction.register(SuaTecnologiaReconstructor())
```

Regras de comportamento:

- Método da porta cuja tecnologia não tenha o conceito devolve **lista
  vazia**, não lança.
- Micro frontend descoberto cujo entrypoint não resolva **aparece no
  resultado** com o que se sabe dele. Sumir é pior que aparecer
  incompleto.
- Arquivo que não parseia é ignorado, não interrompe a varredura.

### B5. Rode e compare

Esta etapa decide se o trabalho prestou. Não a pule.

```
damfe microfrontends <repo> --framework <sua-tecnologia>
damfe reconstruct    <repo> --framework <sua-tecnologia> --out /tmp/art
damfe detect /tmp/art
```

Se você não pode executar comandos, **peça ao usuário que rode e cole a
saída**, e continue a partir dela.

Confira com o usuário:

- A lista de micro frontends está completa? Falta algum? Sobra algum?
- As telas e os fragmentos batem com o que ele espera?
- O `detect()` reconhece o repositório **sem** passar `--framework`?

Se algo não bater, corrija e rode de novo. Mostre a saída real, não só
os arquivos criados.

### B6. Declare o que não foi extraído

Termine listando o que a tecnologia não permitiu determinar
estaticamente, e por quê. Isso vira limitação conhecida documentada — e
vale mais que fingir cobertura completa.

## Erros a evitar

**Reescrever o que já existe.** Se você escreveu um laço recursivo sobre
`node.children`, pare e use `AstReader.walk`. Se está separando nome
importado de alias na mão, use `ImportTable.records`.

**Assumir a forma do single-spa.** O exemplo mostra a estrutura, não é
para ser copiado literalmente. Tecnologia sem orquestrador central não
tem `role == "shell"`. Sem roteamento declarado, `routes` fica vazio e a
extração de navegação devolve lista vazia — isso é correto, não é falha.

**Entregar sem rodar.** Código que importa sem erro não é código que
extrai certo.

**Silenciar o que não deu.** Um resultado vazio sem explicação é pior
que um resultado parcial com a limitação declarada.

---

# Parte C — definir os domínios de negócio

O damfe extrai o que está no código: telas, rotas, fragmentos, serviços
chamados, estado lido. **Domínio de negócio não está lá** — é
conhecimento externo ao repositório, e nenhuma análise estática o
determina.

O que se consegue observar são pistas. Agrupá-las em domínios exige
raciocínio semântico: saber que `cartao`, `compras` e `entregas`
pertencem ao mesmo domínio não decorre do texto, decorre de conhecer o
negócio.

É isso que você vai fazer aqui. O resultado é `.damfe/domains.yml`, que
o usuário revisa e versiona — a partir daí a análise volta a ser
determinística.

## A entrada

Peça ao usuário que gere e cole a listagem de features:

```
damfe reconstruct <repo> --out artifacts
damfe visualize artifacts --format features
```

A saída traz, por micro frontend: as telas com suas rotas, os fragmentos
expostos e compostos, os serviços chamados, o estado global lido, e as
relações entre as partes.

**Trabalhe só com isso.** Não peça para ler o código: a listagem já é a
sumarização, e ir ao código introduz ruído sem acrescentar sinal.

## O que fazer com ela

### C1. Agrupe as pistas em domínios

O sinal mais forte é o **endpoint**, não o nome da tela. `/entregas?cep=`
diz mais sobre o que uma tela faz do que o rótulo `Checkout`. A ordem de
confiança é:

1. caminhos dos serviços chamados
2. rotas das telas
3. fragmentos expostos e consumidos
4. nomes de componentes

Atenção a duas armadilhas do vocabulário:

- **Nomes bilíngues.** `compras` e `purchases`, `produtos` e `products`
  costumam ser o mesmo domínio. Una-os.
- **Rota de navegação não é identidade.** Que o checkout navegue para
  `/products` diz que ele leva o usuário até lá, não que produtos seja
  domínio dele.

### C2. Proponha com evidência

Para cada domínio, diga **quais pistas o sustentam**. Um domínio sem
evidência citada é opinião com aparência de resultado.

> **pagamento** — sustentado por `/cartao`, `/checkout/cards`,
> `/checkout/confirm` e a tela `Cartoes`.

### C3. Confirme com o usuário antes de gravar

Apresente os domínios propostos, com a evidência, e pergunte:

- Os nomes correspondem ao vocabulário que o time usa?
- Falta algum domínio que o sistema tem e a listagem não revelou?
- Algum agrupamento está errado?

**O nome é do usuário, não seu.** Você propõe a partir das pistas; o
vocabulário do negócio é dele. Um domínio bem agrupado com nome errado
atrapalha mais que ajuda, porque parece certo.

### C4. Escreva

`.damfe/domains.yml`, na raiz do repositório analisado:

```yaml
domains:
  pagamento:
    paths: ["/cartao", "/checkout/cards", "/checkout/confirm"]
  pedidos:
    paths: ["/compras", "/checkout/cart", "/checkout/purchases"]
  entrega:
    paths: ["/entregas"]
  catalogo:
    paths: ["/produtos", "/products"]
  identidade:
    paths: ["/login", "/logout", "/usuarios", "/users"]
  enderecos:
    paths: ["/enderecos"]
```

Cada domínio lista os prefixos de caminho que lhe pertencem. Um caminho
não mapeado fica sem domínio, e a ferramenta informa isso — é melhor que
atribuí-lo por chute.

### C5. Diga o que ficou de fora

Termine listando os caminhos que você não conseguiu atribuir, e por quê.
Um mapa incompleto declarado vale mais que um completo inventado.

## Limites que você deve declarar

**Você está inferindo, não medindo.** O agrupamento é julgamento seu
sobre pistas indiretas. Diga isso ao usuário — e que ele é o revisor,
não o destinatário de um veredito.

**Pistas fracas produzem domínios frágeis.** Se a listagem tiver poucos
endpoints, ou nomes genéricos como `Main` e `Page`, o agrupamento fica
fraco. Reconheça em vez de forçar.

**Fronteira de domínio é decisão de projeto.** `pagamento` e `pedidos`
podem legitimamente ser um só domínio ou dois, dependendo de como o
negócio se organiza. Ofereça as duas leituras quando for o caso, em vez
de escolher por conta própria.
