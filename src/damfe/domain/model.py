"""
O modelo neutro de artefatos arquiteturais.

Este módulo é o CONTRATO entre os três módulos do CLI.
Nada aqui pode falar de single-spa, Module Federation ou
qualquer outro framework: quem traduz o vocabulário de um
framework para estes tipos é o módulo de reconstruction.

Detalhes específicos de framework, quando valem a pena,
vão no campo `metadata` de cada entidade.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from damfe.domain.provenance import Provenance

if TYPE_CHECKING:
    from damfe.domain.communication import Communication


@dataclass
class SourceLocation:
    """Onde algo aparece no código-fonte."""

    file: str
    line: int
    code: str | None = None


@dataclass
class RenderLocation:
    """Onde um fragmento é de fato instanciado na interface."""

    file: str
    line: int
    props: list[str] = field(default_factory=list)

    #: As telas em que esta instanciação aparece.
    #:
    #: Saber que `mfe-checkout` consome `DeliveryEstimateFragment`
    #: responde quem depende de quem; saber que ele aparece na tela
    #: de Carrinho responde ONDE aquilo é visto, que é a pergunta de
    #: quem vai mexer no sistema.
    #:
    #: Mais de uma tela é resposta comum e correta: o fragmento pode
    #: estar num componente compartilhado, alcançado a partir de
    #: várias. Vazio significa que nenhuma tela alcança o arquivo —
    #: instanciação em código morto, ou em arquivo que só o shell
    #: monta.
    screens: list[str] = field(default_factory=list)


@dataclass
class CodeSize:
    """
    Tamanho do código de uma unidade.

    `lines` é a contagem física; `code_lines` desconta linhas em
    branco e linhas que são apenas comentário — as segundas
    identificadas pela árvore sintática, não por heurística de
    texto.
    """

    files: int = 0
    lines: int = 0
    code_lines: int = 0


@dataclass
class Fragment:
    """
    Uma unidade de interface que uma aplicação expõe para
    que outras consumam.
    """

    name: str
    microfrontend: str
    file: str | None = None
    line: int = 0

    @property
    def id(self) -> str:
        return f"{self.microfrontend}#{self.name}"


@dataclass
class Screen:
    """Uma tela roteável de uma aplicação."""

    component: str
    microfrontend: str
    route: str | None = None
    route_expression: str = ""
    file: str | None = None
    line: int = 0

    #: Se o componente raiz alcança o arquivo que declara esta tela.
    #:
    #: Uma tela declarada num arquivo que ninguém importa existe no
    #: código e não existe em execução. As duas coisas interessam, e
    #: por motivos diferentes: a reconstrução responde quais telas o
    #: micro frontend define, e esta marca responde quais delas estão
    #: ligadas hoje. Decidir o que fazer com a diferença é de quem lê
    #: o resultado — tela desligada costuma ser refatoração pela
    #: metade, não erro de extração.
    reachable: bool = True

    @property
    def id(self) -> str:
        return f"{self.microfrontend}#{self.component}"


@dataclass
class MicroFrontend:
    """
    Uma unidade de implantação independente — o que o
    single-spa chama de microfrontend e o Module Federation
    chama de remote.

    `role` distingue o orquestrador das demais.
    """

    id: str
    directory: str = ""
    entrypoint: str = ""
    routes: list[str] = field(default_factory=list)
    role: str = "microfrontend"

    #: As unidades que este monta, quando ele é o orquestrador.
    #:
    #: Campo, e não entrada de `metadata`, porque é contrato: toda
    #: tecnologia tem quem componha as demais, e quem escreve um
    #: reconstrutor novo precisa ver isso na porta em vez de
    #: descobrir uma chave combinada em algum lugar. `metadata` é
    #: para o que só faz sentido dentro de uma tecnologia.
    mounts: list[str] = field(default_factory=list)
    fragments: list[Fragment] = field(default_factory=list)
    screens: list[Screen] = field(default_factory=list)
    size: CodeSize = field(default_factory=CodeSize)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Composition:
    """
    Aresta: uma aplicação consome um fragmento de outra.

    `renders` vazio significa import sem uso — o fragmento
    foi importado mas nunca instanciado.
    """

    consumer: str
    provider: str
    fragment: str
    local_name: str
    imported_at: SourceLocation
    renders: list[RenderLocation] = field(default_factory=list)


@dataclass
class ApiCall:
    """
    Aresta: um micro frontend chama um serviço externo.

    Diferente das demais, esta aresta não liga dois micro
    frontends — liga um deles a um endereço fora do sistema. O
    acoplamento aparece quando dois consomem o mesmo endpoint.

    `path` costuma ser relativo, porque a base normalmente vem de
    variável de ambiente e não é determinável estaticamente.

    `screens` e `fragments` dizem quem alcança a chamada seguindo
    os imports internos do micro frontend. São listas porque um
    módulo de serviço compartilhado é alcançado por várias telas —
    e ficam vazias quando a chamada não é alcançável a partir de
    nenhuma delas, o que também é informação.
    """

    microfrontend: str
    method: str
    path: str
    match: str
    client: str
    at: SourceLocation
    screens: list[str] = field(default_factory=list)
    fragments: list[str] = field(default_factory=list)


@dataclass
class Endpoint:
    """
    Um serviço externo consumido pelo sistema.

    É o único nó do modelo que está FORA da fronteira: ninguém o
    implanta, ninguém o versiona junto, e mesmo assim dois micro
    frontends que o chamam estão acoplados pelo contrato dele. Sem
    ele, esse acoplamento não tinha onde morar — `ApiCall` guardava
    o caminho como texto, e o "mesmo endpoint" do `hammering-apis`
    não era uma coisa, era uma coincidência de string.

    Derivado das chamadas, não extraído: o caminho é a identidade,
    e os métodos são os verbos vistos sobre ele.
    """

    path: str
    methods: list[str] = field(default_factory=list)

    #: quem o chama, por identificador
    microfrontends: list[str] = field(default_factory=list)


@dataclass
class StateAccess:
    """
    Um micro frontend LÊ uma parte do estado global.

    Acoplamento sem mensagem e sem import: dois micro frontends que
    leem a mesma fatia dependem do mesmo formato de dado, e uma
    mudança nela quebra os dois — ainda que não se conheçam.

    Só leitura, deliberadamente. A escrita existe e também acopla,
    mas o que o código revela no ponto da chamada é o nome da ação
    despachada, não a fatia alterada — descobrir a fatia exigiria
    seguir o redutor, que pode viver noutro pacote. Registrar as
    duas na mesma lista misturaria dois vocabulários: caminho de
    estado e nome de ação não são a mesma coisa.
    """

    microfrontend: str
    library: str
    path: str
    at: SourceLocation


@dataclass
class Navigation:
    """
    Aresta: código de uma aplicação leva o usuário para uma
    rota pertencente a outra.

    `match` diz o grau de confiança: `exact` quando a URL foi
    resolvida por inteiro, `prefix` quando só o começo dela
    pôde ser determinado estaticamente.
    """

    source: str
    target: str
    expression: str
    resolved_url: str | None
    match: str
    at: SourceLocation


@dataclass
class MicroFrontendArchitecture:
    """Tudo que a reconstrução extraiu de um repositório."""

    #: nome do projeto analisado, para identificar o relatório.
    #: Só o nome, nunca o caminho absoluto — o artefato é
    #: versionado, e caminho de máquina sujaria o diff.
    project: str = ""
    microfrontends: list[MicroFrontend] = field(default_factory=list)
    compositions: list[Composition] = field(default_factory=list)
    navigations: list[Navigation] = field(default_factory=list)
    communications: list["Communication"] = field(default_factory=list)
    api_calls: list[ApiCall] = field(default_factory=list)
    state_accesses: list[StateAccess] = field(default_factory=list)

    #: De onde isto veio: versão do esquema, versão da ferramenta,
    #: extrator usado e a revisão de cada repositório lido.
    provenance: "Provenance" = field(default_factory=Provenance)

    def microfrontend(self, identifier: str) -> MicroFrontend | None:

        for microfrontend in self.microfrontends:

            if microfrontend.id == identifier:
                return microfrontend

        return None

    @property
    def fragments(self) -> list[Fragment]:

        return [
            fragment
            for microfrontend in self.microfrontends
            for fragment in microfrontend.fragments
        ]

    @property
    def endpoints(self) -> list["Endpoint"]:
        """
        Os serviços externos, agrupados pelas chamadas.

        Derivado, como `fragments` e `screens`: não é coleção
        gravada, é a leitura das chamadas por caminho.
        """

        grouped: dict[str, Endpoint] = {}

        for call in self.api_calls:

            endpoint = grouped.setdefault(call.path, Endpoint(path=call.path))

            if call.method not in endpoint.methods:
                endpoint.methods.append(call.method)

            if call.microfrontend not in endpoint.microfrontends:
                endpoint.microfrontends.append(call.microfrontend)

        return [grouped[path] for path in sorted(grouped)]

    @property
    def screens(self) -> list[Screen]:

        return [
            screen
            for microfrontend in self.microfrontends
            for screen in microfrontend.screens
        ]
