# damfe

Análise estática de arquiteturas micro frontend. Extrai do código-fonte
os artefatos que descrevem a arquitetura, detecta anti-padrões sobre eles
e gera visualizações.

Hoje reconhece **single-spa**. Outras tecnologias entram como extensão,
sem alterar os demais módulos.

Nenhuma etapa da análise usa modelo de linguagem, rede ou execução do
código analisado. Ver [docs/architecture.md](docs/architecture.md).

## Instalação

```bash
cd damfe
pipx install -e .
```

O `-e` deixa a instalação editável: mudanças no código valem na hora. O
comando `damfe` fica disponível globalmente.

## Uso em cinco minutos

```bash
damfe analyze /caminho/do/repo --prefix @sua-org/
```

Reconstrói, detecta e visualiza numa passada, gravando em `artifacts/`.
Os três passos também existem em separado, para quem precisa deles:

```bash
damfe reconstruct /caminho/do/repo --prefix @sua-org/ --out artifacts
damfe detect artifacts --out artifacts
damfe visualize artifacts --detections artifacts
```

Para depurar um extrator, `--only` recorta uma coleção:

```bash
damfe reconstruct /caminho/do/repo --prefix @sua-org/ --only navigations
```

Saída típica:

```
4 micro frontends, 4 fragmentos, 12 telas, 4 imports e 18 navegações
  e 0 comunicações entre micro frontends · 16 chamadas externas
  · 8 acessos ao estado global

cyclic-dependency  [importação de fragmento]
  Ciclo: mfe-checkout → mfe-products → mfe-checkout
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
damfe reconstruct <repo> [--prefix PREFIX] [--framework FRAMEWORK] [--out DIR]
```

| opção | padrão | descrição |
|---|---|---|
| `--prefix` | nenhum | filtra os micro frontends pelo prefixo da organização, ex.: `@nabstore/` |
| `--framework` | detectado | força um extrator. Hoje só `single-spa` |
| `--out` | `artifacts` | diretório de saída |

### Extrações parciais

Cada etapa roda sozinha e imprime no terminal, sem gravar:

```bash
damfe microfrontends <repo>     # inventário: rotas, telas, fragmentos, tamanho
damfe fragment-imports <repo>   # quem usa componente de quem
damfe navigations <repo>        # quem leva o usuário para onde
damfe api-calls <repo>          # quem chama qual serviço externo
damfe global-state <repo>       # quem lê qual fatia do estado global
damfe communications <repo>     # quem manda mensagem para quem
```

Todas aceitam `--prefix` e `--framework`.

### `detect` — aplica as regras

```bash
damfe detect [artifacts] [--rule NOME] [--out DIR]
```

| opção | padrão | descrição |
|---|---|---|
| `artifacts` | `artifacts` | diretório com os artefatos |
| `--rule` | todas | aplica só esta regra. Pode repetir |
| `--out` | nenhum | grava `detections.json` |

### `visualize` — desenha

```bash
damfe visualize [artifacts] [--format FORMATO] [--detections ARQUIVO] [--out ARQUIVO]
```

| formato | saída |
|---|---|
| `html` | relatório único, autocontido, sem CDN |
| `features` | sumarização em Markdown do sistema |

### `setup-communication`

```bash
damfe setup-communication <repo>   # gera .damfe/communication.yml
```

---

## Artefatos produzidos

| arquivo | conteúdo |
|---|---|
| `manifest.json` | o envelope: versão do esquema, procedência e índice |
| `microfrontends.json` | os nós: rotas, papel, telas, fragmentos, tamanho |
| `fragment_imports.json` | consumo de componente entre micro frontends |
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
  "damfe": "1.0.0",
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

`damfe` é a versão do **esquema** dos artefatos e sobe quando a forma
dos arquivos quebra quem os lê; `tool_version` é a da **ferramenta**.
São separadas porque corrigir um bug num extrator muda a segunda e não
a primeira — e uma coleta longa precisa poder afirmar que todos os
resultados seguem o mesmo esquema.

`sources[]` lista os repositórios lidos, procurados até dois níveis
abaixo da raiz — é como o `damfe setup` é usado, numa pasta com vários
clones. O `commit` é o que permite repetir a análise sobre exatamente o
mesmo código; `dirty` avisa que havia alteração não commitada e que,
portanto, o `commit` *não* identifica o que foi lido. Credencial
embutida na URL de origem é removida antes de gravar.

Sem git instalado ou fora de um repositório, `sources` vem vazio e a
análise segue normalmente.

A saída é JSON e a entrada é YAML, de propósito: `.damfe/*.yml` é
escrito à mão e ganha comentários; `artifacts/*.json` é gerado e
consumido por máquina. O porquê está em
[docs/decisions.md](docs/decisions.md), seção 9.

### Como os artefatos são descobertos

**Micro frontends** vêm do `registerApplication` do orquestrador — o
contrato do single-spa. Isso encontra também aplicações sem pacote
próprio.

**Fragmentos** são os exports do entrypoint que não fazem parte do
contrato de lifecycle.

**Telas** vêm das `<Route>` declaradas pelo `rootComponent`.

**Tamanho** é medido durante a mesma varredura, com as linhas de
comentário descontadas pela árvore sintática — não por prefixo de texto.

**Navegações** usam uma inversão: em vez de procurar chamadas de
navegação, que variam por roteador, o extrator procura expressões que
resolvem para uma rota de OUTRO micro frontend. O dono da rota vem do
`activeWhen`, que é padronizado.

**Chamadas externas** são reconhecidas em três camadas: `fetch` e
`XMLHttpRequest`, que são API da plataforma web; clientes conhecidos
— axios, ky, got, superagent — identificados pelo especificador do
import, incluindo instâncias de `axios.create()`; e o caminho é
resolvido pelo mesmo avaliador parcial das rotas. Cada chamada registra
as telas que a alcançam seguindo os imports internos.

**Estado global** vem de bibliotecas conhecidas pelo import — react-redux,
zustand, jotai, recoil, mobx, pinia. Só **leitura**: o seletor percorre o
caminho explicitamente, enquanto a escrita revela apenas o nome da ação.

**Comunicação** tem três camadas: primitivas da plataforma
(`CustomEvent` com `dispatchEvent`/`addEventListener`,
`BroadcastChannel`), barramentos conhecidos por import, e o mecanismo
declarado pelo usuário.

---

## Declarações por projeto

Ficam em `.damfe/`, na raiz do repositório analisado — versionadas com
ele, e imunes à limpeza da pasta de saída.

### `.damfe/communication.yml`

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

Micro frontends que dependem uns dos outros em ciclo. Avalia as três
relações **separadamente**, porque um ciclo significa coisas diferentes
em cada uma: composição é acoplamento de build; navegação em ciclo
costuma ser fluxo legítimo do produto.

### `hub-like-dependency`

Tela que instancia muitos fragmentos. O sinal é a quantidade de
**fragmentos**, não de provedores: cinco fragmentos de um provedor só
concentram tanta mudança de contrato quanto cinco de cinco. Padrão 5.

### `one-for-all`

Micro frontend ligado a quase todos os demais. Conta vizinhos sem
direção, mas registra separadamente de quem depende e por quem é
dependido — gargalo compartilhado e excesso de conhecimento são
problemas distintos. Exclui o orquestrador e se abstém em sistemas
pequenos.

### `hammering-apis`

Rota de serviço consumida por mais de um micro frontend. Agrupa por
**caminho**, não por caminho mais método: quem lê e quem escreve no
mesmo recurso compartilham o mesmo contrato.

### `global-state-communication`

Estado global lido por mais de um micro frontend. Ocorrência **única e
binária**: o sistema usa estado como canal ou não usa.

### `mega-frontend`

Micro frontend cujas telas **e** linhas de código ficam acima de `2×` a
mediana do sistema. Indica concentração de responsabilidades, mas não
prova: uma unidade grande e coesa não é um Mega Frontend.

### `nano-frontend`

Micro frontend cujas telas somadas aos fragmentos ficam abaixo de
`0.4×` a mediana do sistema. Indica fragmentação excessiva, mas não
prova: uma unidade pequena é legítima quando constitui sozinha uma
capacidade inteira.

### Sem escala de severidade

Atribuir "alta" ou "baixa" exigiria um critério definido e justificado.
No lugar, cada ocorrência informa a **dimensão** — qual relação
arquitetural a produziu.

---

## Limitações conhecidas

**Propagação de constantes** é indexada pelo nome do identificador,
globalmente. Dois arquivos com uma `const routes` diferente colidem.

**Descoberta por `registerApplication` literal.** Projetos que usam
`single-spa-layout` geram os registros a partir de um layout e não têm a
chamada no código.

**`activeWhen` como função** não é resolvível estaticamente.

**Destino de navegação dinâmico** (`navigate(variavel)`) não resolve.
Literais, constantes, templates e `.replace(":id", …)` resolvem.

**Navegação dentro de fragmento** é atribuída ao micro frontend que
define o fragmento, não ao que o renderiza.

**Fragmento instanciado fora do arquivo da tela** não é atribuído a ela
pelo `hub-like-dependency`, que liga fragmento a tela pelo arquivo.

**Escrita no estado global** não é extraída: a chamada revela o nome da
ação, não a fatia alterada.

**`baseURL` não resolve**, porque vem de variável de ambiente. Os
caminhos ficam relativos, e dois micro frontends falando com serviços
diferentes no mesmo caminho parecem iguais.

**GraphQL não cabe no modelo** de chamada externa: tudo vai para um
endpoint só, e a unidade real é a operação.

**Mudar uma declaração exige refazer o `reconstruct`.** Editar
`communication.yml` e rodar só o `detect` usa a resolução anterior, sem
aviso.

**Versões do tree-sitter estão fixadas numa faixa fechada.** O núcleo e
os bindings de linguagem compartilham uma ABI, e misturar famílias
corrompe memória silenciosamente — o processo morre por falha de
segmentação em lugares aleatórios, sem exceção.
