"""
Ciclo de dependência entre micro frontends.

Micro frontends existem para poder ser implantados de forma
independente. Um ciclo quebra essa premissa: nenhuma das partes
do ciclo pode evoluir sem considerar as outras.

A regra procura ciclos DENTRO DE UMA MESMA TELA. Num grafo do
sistema inteiro, arestas que nunca coexistem em execução se
encadeiam — a composição de uma tela com a comunicação de outra —
e em sistema grande o número de ciclos explode sem que nenhum deles
seja montado de fato. Numa tela, as partes do ciclo estão no ar ao
mesmo tempo, e é aí que o acoplamento se manifesta.

Estar na tela significa ser alcançado por ela: o código que o
componente da tela importa, os fragmentos que ele renderiza e, em
qualquer profundidade, os fragmentos que esses renderizam. Micro
frontends montados lado a lado pelo orquestrador, sem que a tela
os renderize, não entram.

As relações continuam avaliadas separadamente, porque um ciclo
significa coisas diferentes em cada uma. Navegação não entra: ela
liga uma tela a OUTRA, e ida e volta entre telas é fluxo do produto,
não acoplamento.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

import networkx as nx

from mfad.adapters.driven import i18n
from mfad.application.ports import Rule
from mfad.domain import (
    AntiPattern,
    AntiPatternDetection,
    MicroFrontendArchitecture,
    Placement,
    SourceLocation,
)


@dataclass(frozen=True)
class Edge:
    """Uma aresta de uma relação, já situada nas telas em que acontece."""

    source: str
    target: str
    label: str
    locations: list[SourceLocation]
    screens: frozenset[str]


@dataclass(frozen=True)
class Relation:
    """Uma família de arestas e o que um ciclo nela significa."""

    key: str

    #: chaves de texto em `i18n/texts.json`: o nome da relação e o
    #: que um ciclo nela significa
    label: str
    explanation: str

    edges: Callable[["Stage"], Iterable[Edge]]


@dataclass
class Stage:
    """
    O que cada tela monta, em qualquer profundidade de fragmento.

    Calculado uma vez e compartilhado pelas relações, porque as duas
    fazem a mesma pergunta — em que telas este trecho de código está
    no ar — e a resposta depende só das composições.
    """

    architecture: MicroFrontendArchitecture

    #: tela → fragmentos montados nela, transitivamente
    fragments: dict[str, set[str]] = field(default_factory=dict)

    def __post_init__(self):

        screens = {screen.id for screen in self.architecture.screens}

        # Uma instanciação é alcançada por telas diretamente e por
        # fragmentos quando está dentro de outro fragmento. O fecho
        # parte das telas e desce pelos fragmentos montados.
        by_screen: dict[str, set[str]] = {}
        by_fragment: dict[str, set[str]] = {}

        for item in self.architecture.compositions:

            mounted = f"{item.provider}#{item.fragment}"

            for render in item.renders:

                for screen in render.screens:
                    by_screen.setdefault(screen, set()).add(mounted)

                for fragment in render.fragments:
                    by_fragment.setdefault(fragment, set()).add(mounted)

        for screen in screens | set(by_screen):

            seen: set[str] = set()
            pending = list(by_screen.get(screen, ()))

            while pending:

                current = pending.pop()

                if current in seen:
                    continue

                seen.add(current)
                pending.extend(by_fragment.get(current, set()) - seen)

            self.fragments[screen] = seen

    def screens_of(self, placement: Placement) -> frozenset[str]:
        """As telas em que um trecho de código está no ar."""

        found = set(placement.screens)

        if placement.fragments:

            reached = set(placement.fragments)

            found.update(
                screen
                for screen, mounted in self.fragments.items()
                if mounted & reached
            )

        return frozenset(found)


def _composition_edges(stage: Stage):

    for item in stage.architecture.compositions:

        for render in item.renders:

            screens = stage.screens_of(
                Placement(screens=render.screens, fragments=render.fragments)
            )

            if screens:
                yield Edge(
                    item.consumer,
                    item.provider,
                    item.fragment,
                    [SourceLocation(file=render.file, line=render.line)],
                    screens,
                )


def _communication_edges(stage: Stage):
    """
    Só as arestas cujo sentido significa alguma coisa, e só nas
    telas em que as duas pontas estão no ar.

    Uma aresta simétrica — acoplamento por estado compartilhado, hoje
    — é representada como um par de arestas opostas, então procurar
    ciclo nela encontra um em toda dupla, por construção. O ciclo
    seria a codificação, não o sistema.

    O teste é a propriedade, não o mecanismo: qualquer meio simétrico
    que venha a existir já entra certo, sem a regra precisar conhecer
    o nome dele.
    """

    for item in stage.architecture.communications:

        if not item.directed:
            continue

        screens = stage.screens_of(item.produced_on) & stage.screens_of(
            item.consumed_on
        )

        if screens:
            yield Edge(
                item.source,
                item.target,
                item.channel,
                item.produced_at + item.consumed_at,
                screens,
            )


RELATIONS = (
    Relation(
        key="composition",
        label="dimension.fragment_import",
        explanation="cycle.explanation.composition",
        edges=_composition_edges,
    ),
    Relation(
        key="communication",
        label="dimension.communication",
        explanation="cycle.explanation.communication",
        edges=_communication_edges,
    ),
)


@dataclass
class _Found:
    """Um ciclo, juntado de todas as telas em que aparece."""

    cycle: list[str]
    screens: set[str] = field(default_factory=set)
    labels: set[str] = field(default_factory=set)
    locations: dict[tuple, SourceLocation] = field(default_factory=dict)


class CyclicDependency(Rule):

    anti_pattern = AntiPattern(
        name="cyclic-dependency",
        description=(
            "Micro frontends que dependem uns dos outros em ciclo "
            "dentro de uma mesma tela, por importação de fragmento "
            "ou por comunicação."
        ),
        category="Inter-frontend",
        reference="https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Cyclic%20Dependency",
    )

    #: Enumerar ciclos elementares custa proporcional à QUANTIDADE
    #: de ciclos, que cresce exponencialmente num grafo denso. Este
    #: teto evita que um grafo patológico trave a execução.
    MAX_CYCLES = 200

    def check(self, architecture: MicroFrontendArchitecture) -> list[AntiPatternDetection]:

        stage = Stage(architecture)

        detections: list[AntiPatternDetection] = []

        for relation in RELATIONS:
            detections.extend(self._cycles(stage, relation))

        return detections

    def _cycles(
        self,
        stage: Stage,
        relation: Relation,
    ) -> list[AntiPatternDetection]:

        # Um grafo por tela. Montar um só grafo e filtrar os ciclos
        # depois não serviria: a enumeração é que explode, e ela
        # percorreria justamente as combinações que nunca coexistem.
        graphs: dict[str, nx.DiGraph] = {}

        for edge in relation.edges(stage):

            for screen in edge.screens:

                graph = graphs.setdefault(screen, nx.DiGraph())

                if not graph.has_edge(edge.source, edge.target):
                    graph.add_edge(
                        edge.source, edge.target, labels=[], locations=[]
                    )

                data = graph.edges[edge.source, edge.target]
                data["labels"].append(edge.label)
                data["locations"].extend(edge.locations)

        # O mesmo ciclo costuma aparecer em várias telas — um
        # fragmento compartilhado leva o ciclo junto. Uma ocorrência
        # por ciclo, com as telas listadas, e não uma por tela.
        found: dict[tuple[str, ...], _Found] = {}

        for screen in sorted(graphs):

            graph = graphs[screen]

            for cycle in nx.simple_cycles(graph):

                key = self._canonical(cycle)

                if key not in found:

                    if len(found) >= self.MAX_CYCLES:
                        break

                    found[key] = _Found(cycle=list(key))

                self._collect(found[key], graph, screen)

        return [
            self._detection(item, relation)
            for _, item in sorted(found.items())
        ]

    @staticmethod
    def _canonical(cycle: list[str]) -> tuple[str, ...]:
        """O ciclo começando pelo menor nó, para casar entre telas."""

        start = cycle.index(min(cycle))

        return tuple(cycle[start:] + cycle[:start])

    @staticmethod
    def _collect(item: _Found, graph: nx.DiGraph, screen: str) -> None:

        item.screens.add(screen)

        for position, node in enumerate(item.cycle):

            target = item.cycle[(position + 1) % len(item.cycle)]

            data = graph.edges[node, target]

            item.labels.update(data["labels"])

            for location in data["locations"]:
                item.locations.setdefault(
                    (location.file, location.line), location
                )

    def _detection(
        self,
        item: _Found,
        relation: Relation,
    ) -> AntiPatternDetection:

        cycle = item.cycle
        screens = sorted(item.screens)

        text = {
            "dimension": i18n.ref(relation.label),
            "explanation": i18n.ref(relation.explanation),
            "message": i18n.ref(
                "cycle.message",
                relation=i18n.ref(relation.label),
                where=i18n.ref("cycle.where", n=len(screens), screen=self._short(screens[0])),
                chain=" → ".join(self._short(node) for node in cycle)
                + f" → {self._short(cycle[0])}",
            ),
        }

        text["facts"] = [
            i18n.fact("fact.relation", i18n.ref(relation.label)),
            i18n.fact("fact.where", i18n.ref("cycle.where", n=len(screens), screen=self._short(screens[0]))),
            i18n.fact(
                "fact.cycle",
                " → ".join(self._short(node) for node in cycle) + f" → {self._short(cycle[0])}",
            ),
        ]

        return AntiPatternDetection(
            anti_pattern=self.name,
            dimension=i18n.t(text["dimension"]),
            explanation=i18n.t(text["explanation"]),
            message=i18n.t(text["message"]),
            subjects=list(cycle),
            locations=[
                item.locations[key] for key in sorted(item.locations)
            ],
            metadata={
                "text": text,
                "relation": relation.key,
                "edges": [
                    [node, cycle[(position + 1) % len(cycle)]]
                    for position, node in enumerate(cycle)
                ],
                # A cadeia é declarada, e não inferida das arestas:
                # só um ciclo tem ordem, e pares de uma relação sem
                # direção seriam lidos como caminho se a página
                # tentasse deduzir.
                "chain": cycle + [cycle[0]],
                "length": len(cycle),
                "through": sorted(item.labels),
                "screens": screens,
            },
        )

    @staticmethod
    def _short(name: str) -> str:

        return name.rpartition("/")[2] or name
