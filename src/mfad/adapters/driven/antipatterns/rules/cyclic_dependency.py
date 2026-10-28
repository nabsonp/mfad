"""
Dependency cycle between micro frontends.

Micro frontends exist so they can be deployed independently. A
cycle breaks that premise: none of the parts of the cycle can evolve
without considering the others.

The rule looks for cycles WITHIN A SINGLE SCREEN. In a graph of the
whole system, edges that never coexist at runtime get chained — the
composition of one screen with the communication of another — and in
a large system the number of cycles explodes without any of them
actually being mounted. On a screen, the parts of the cycle are live
at the same time, and that is where the coupling shows up.

Being on the screen means being reached by it: the code the screen
component imports, the fragments it renders and, at any depth, the
fragments those render. Micro frontends mounted side by side by the
orchestrator, without the screen rendering them, are not included.

The relations are still evaluated separately, because a cycle means
different things in each one. Navigation is not included: it links
one screen to ANOTHER, and going back and forth between screens is
product flow, not coupling.
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
    """An edge of a relation, already placed on the screens where it happens."""

    source: str
    target: str
    label: str
    locations: list[SourceLocation]
    screens: frozenset[str]


@dataclass(frozen=True)
class Relation:
    """A family of edges and what a cycle in it means."""

    key: str

    #: text keys in `i18n/texts.json`: the name of the relation and
    #: what a cycle in it means
    label: str
    explanation: str

    edges: Callable[["Stage"], Iterable[Edge]]


@dataclass
class Stage:
    """
    What each screen mounts, at any fragment depth.

    Computed once and shared by the relations, because both ask the
    same question — on which screens is this piece of code live — and
    the answer depends only on the compositions.
    """

    architecture: MicroFrontendArchitecture

    #: screen → fragments mounted on it, transitively
    fragments: dict[str, set[str]] = field(default_factory=dict)

    def __post_init__(self):

        screens = {screen.id for screen in self.architecture.screens}

        # An instantiation is reached by screens directly and by
        # fragments when it is inside another fragment. The closure
        # starts from the screens and descends through the mounted
        # fragments.
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
        """The screens on which a piece of code is live."""

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
    Only the edges whose direction means something, and only on the
    screens where both ends are live.

    A symmetric edge — coupling through shared state, today — is
    represented as a pair of opposite edges, so looking for a cycle in
    it finds one in every pair, by construction. The cycle would be
    the encoding, not the system.

    The test is the property, not the mechanism: any symmetric means
    that comes to exist is already handled correctly, without the
    rule needing to know its name.
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
    """A cycle, gathered from all the screens where it appears."""

    cycle: list[str]
    screens: set[str] = field(default_factory=set)
    labels: set[str] = field(default_factory=set)
    locations: dict[tuple, SourceLocation] = field(default_factory=dict)


class CyclicDependency(Rule):

    anti_pattern = AntiPattern(
        name="cyclic-dependency",
        description=(
            "Micro frontends that depend on each other in a cycle "
            "within the same screen, through fragment import "
            "or through communication."
        ),
        category="Inter-frontend",
        reference="https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Cyclic%20Dependency",
    )

    #: Enumerating elementary cycles costs in proportion to the NUMBER
    #: of cycles, which grows exponentially in a dense graph. This cap
    #: keeps a pathological graph from stalling the run.
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

        # One graph per screen. Building a single graph and filtering
        # the cycles afterwards would not work: the enumeration is what
        # explodes, and it would walk exactly the combinations that
        # never coexist.
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

        # The same cycle often appears on several screens — a shared
        # fragment carries the cycle along. One occurrence per cycle,
        # with the screens listed, not one per screen.
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
        """The cycle starting from the smallest node, to match across screens."""

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
                # The chain is declared, not inferred from the edges:
                # only a cycle has an order, and pairs from an
                # undirected relation would be read as a path if the
                # page tried to deduce it.
                "chain": cycle + [cycle[0]],
                "length": len(cycle),
                "through": sorted(item.labels),
                "screens": screens,
            },
        )

    @staticmethod
    def _short(name: str) -> str:

        return name.rpartition("/")[2] or name
