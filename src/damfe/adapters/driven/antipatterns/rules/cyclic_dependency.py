"""
Ciclo de dependência entre micro frontends.

Micro frontends existem para poder ser implantados de forma
independente. Um ciclo quebra essa premissa: nenhuma das partes
do ciclo pode evoluir sem considerar as outras.

A regra avalia as três relações separadamente, e não num grafo
único, porque um ciclo significa coisas diferentes em cada uma —
e a gravidade acompanha essa diferença.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

import networkx as nx

from damfe.application.ports import Rule
from damfe.domain import AntiPattern, AntiPatternDetection, MicroFrontendArchitecture, SourceLocation


@dataclass(frozen=True)
class Relation:
    """Uma família de arestas e o que um ciclo nela significa."""

    key: str
    label: str
    explanation: str
    edges: Callable[[MicroFrontendArchitecture], Iterable]


def _composition_edges(architecture: MicroFrontendArchitecture):

    for item in architecture.compositions:
        yield item.consumer, item.provider, item.fragment, [
            item.imported_at
        ]


def _navigation_edges(architecture: MicroFrontendArchitecture):

    for item in architecture.navigations:
        yield item.source, item.target, item.resolved_url, [item.at]


def _communication_edges(architecture: MicroFrontendArchitecture):
    """
    Só as arestas cujo sentido significa alguma coisa.

    Uma aresta simétrica — acoplamento por estado compartilhado, hoje
    — é representada como um par de arestas opostas, então procurar
    ciclo nela encontra um em toda dupla, por construção. O ciclo
    seria a codificação, não o sistema.

    O teste é a propriedade, não o mecanismo: qualquer meio simétrico
    que venha a existir já entra certo, sem a regra precisar conhecer
    o nome dele.
    """

    for item in architecture.communications:

        if not item.directed:
            continue

        yield item.source, item.target, item.channel, (
            item.produced_at + item.consumed_at
        )


RELATIONS = (
    Relation(
        key="composition",
        label="importação de fragmento",
        explanation=(
            "acoplamento de build: as partes não podem ser "
            "construídas nem implantadas separadamente"
        ),
        edges=_composition_edges,
    ),
    Relation(
        key="communication",
        label="comunicação",
        explanation=(
            "acoplamento de contrato: uma mudança de mensagem "
            "se propaga em volta do ciclo"
        ),
        edges=_communication_edges,
    ),
    Relation(
        key="navigation",
        label="navegação",
        explanation=(
            "ida e volta entre telas costuma ser fluxo legítimo; "
            "só indica acoplamento se as rotas forem conhecidas "
            "por dentro do código em vez de configuradas"
        ),
        edges=_navigation_edges,
    ),
)


class CyclicDependency(Rule):

    anti_pattern = AntiPattern(
        name="cyclic-dependency",
        description=(
            "Micro frontends que dependem uns dos outros em ciclo, "
            "por importação de fragmento, comunicação ou navegação."
        ),
        category="Inter-frontend",
        reference="https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Cyclic%20Dependency",
    )

    #: Enumerar ciclos elementares custa proporcional à QUANTIDADE
    #: de ciclos, que cresce exponencialmente num grafo denso. Este
    #: teto evita que um grafo patológico trave a execução.
    MAX_CYCLES = 200

    def check(self, architecture: MicroFrontendArchitecture) -> list[AntiPatternDetection]:

        detections: list[AntiPatternDetection] = []

        for relation in RELATIONS:
            detections.extend(self._cycles(architecture, relation))

        return detections

    def _cycles(
        self,
        architecture: MicroFrontendArchitecture,
        relation: Relation,
    ) -> list[AntiPatternDetection]:

        graph = nx.DiGraph()

        for source, target, label, locations in relation.edges(architecture):

            if graph.has_edge(source, target):

                data = graph.edges[source, target]
                data["labels"].append(label)
                data["locations"].extend(locations)

            else:
                graph.add_edge(
                    source,
                    target,
                    labels=[label],
                    locations=list(locations),
                )

        detections: list[AntiPatternDetection] = []

        for index, cycle in enumerate(nx.simple_cycles(graph)):

            if index >= self.MAX_CYCLES:
                break

            detections.append(self._detection(graph, cycle, relation))

        return detections

    def _detection(
        self,
        graph: nx.DiGraph,
        cycle: list[str],
        relation: Relation,
    ) -> AntiPatternDetection:

        labels: list[str] = []
        locations: list[SourceLocation] = []
        edges: list[list[str]] = []

        for position, node in enumerate(cycle):

            target = cycle[(position + 1) % len(cycle)]

            data = graph.edges[node, target]

            labels.extend(data["labels"])
            locations.extend(data["locations"])
            edges.append([node, target])

        return AntiPatternDetection(
            anti_pattern=self.name,
            dimension=relation.label,
            explanation=relation.explanation,
            message=(
                f"Ciclo de {relation.label}: "
                + " → ".join(self._short(item) for item in cycle)
                + f" → {self._short(cycle[0])}"
            ),
            subjects=list(cycle),
            locations=locations,
            metadata={
                "relation": relation.key,
                "edges": edges,
                # A cadeia é declarada, e não inferida das arestas:
                # só um ciclo tem ordem, e pares de uma relação sem
                # direção seriam lidos como caminho se a página
                # tentasse deduzir.
                "chain": cycle + [cycle[0]],
                "length": len(cycle),
                "through": sorted(set(labels)),
            },
        )

    @staticmethod
    def _short(name: str) -> str:

        return name.rpartition("/")[2] or name
