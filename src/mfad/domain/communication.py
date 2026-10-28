"""
Communication between applications and the declaration of the mechanism.

Unlike routes and fragments, communication has no single contract in
the ecosystem: each project picks an event bus, a shared store,
`window`, `postMessage`. That is why the mechanism is DECLARED once,
at a setup moment, and extraction then becomes as deterministic as
the others.

`Communication` is the result; `CommunicationSpec` is the declaration.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mfad.domain.model import Placement, SourceLocation, StateAccess


@dataclass
class ChannelOperation:
    """
    One side of the mechanism: who publishes or who subscribes.

    `module` and `export` identify the function; `channel_argument`
    tells at which argument position the channel name is.
    """

    module: str
    export: str
    channel_argument: int = 0


@dataclass
class Mechanism:
    """A communication medium declared by the user."""

    name: str
    kind: str
    produce: ChannelOperation
    consume: ChannelOperation


@dataclass
class CommunicationSpec:
    """What the setup wrote. Empty means setup not done."""

    mechanisms: list[Mechanism] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.mechanisms)


@dataclass
class Communication:
    """
    Edge: one application publishes on a channel that another subscribes to.

    Producers and consumers are paired by CHANNEL NAME, not by call —
    the channel is the contract between the two ends.
    """

    source: str
    target: str
    mechanism: str
    channel: str
    produced_at: list[SourceLocation] = field(default_factory=list)
    consumed_at: list[SourceLocation] = field(default_factory=list)

    #: Screens and fragments that reach each end.
    #:
    #: The two sides of a channel only actually talk when they are
    #: mounted at the same time. Without knowing where each end is, a
    #: producer on one screen and a consumer on another became an edge,
    #: and the graph linked parts that never coexist.
    produced_on: Placement = field(default_factory=Placement)
    consumed_on: Placement = field(default_factory=Placement)

    #: Whether the direction of the edge means anything.
    #:
    #: A message has sides: whoever publishes is not whoever subscribes.
    #: Coupling through shared state does not — both read, neither is
    #: the origin —, and the symmetry is represented by a pair of
    #: opposite edges, for lack of an undirected type in the collection.
    #:
    #: Whoever traverses the graph needs to know the difference.
    #: Searching for a cycle among symmetric edges finds one in every
    #: pair, and the cycle is the encoding, not the system.
    directed: bool = True


def edges_from_state(accesses: list[StateAccess]) -> list[Communication]:
    """
    Global-state coupling, as edges of the same graph.

    When two micro frontends read the same slice, the shape of that
    data has become a de facto public interface between them:
    changing it breaks both at once. That is communication, even
    though no message is passed, and leaving it out of the graph made
    the rules that traverse it — cycle, hub — undercount the real
    coupling.

    The edge is UNDIRECTED, and that is where it differs from all the
    others in this collection. A message has sides: someone
    publishes, someone subscribes. A shared read does not — three
    readers of the same slice depend on each other mutually, with
    none being the origin. Since `Communication` has `source` and
    `target`, each pair becomes TWO edges, one in each direction, and
    the pair is ordered by name so that the result does not depend on
    the extraction order.

    Only reads go in, because only they are extracted — see
    `StateAccess` on why writes are left out.
    """

    by_path: dict[tuple[str, str], set[str]] = {}
    locations: dict[tuple[str, str, str], list[SourceLocation]] = {}

    for access in accesses:

        key = (access.library, access.path)

        by_path.setdefault(key, set()).add(access.microfrontend)

        locations.setdefault(
            (access.library, access.path, access.microfrontend), []
        ).append(access.at)

    edges = []

    for (library, path), readers in sorted(by_path.items()):

        if len(readers) < 2:
            continue

        for source in sorted(readers):
            for target in sorted(readers):

                if source == target:
                    continue

                edges.append(
                    Communication(
                        source=source,
                        target=target,
                        mechanism="global-state",
                        channel=f"{library}:{path}",
                        produced_at=locations[(library, path, source)],
                        consumed_at=locations[(library, path, target)],
                        directed=False,
                    )
                )

    return edges
