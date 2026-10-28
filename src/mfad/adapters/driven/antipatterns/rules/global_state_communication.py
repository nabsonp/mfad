"""
Global state used as a channel between micro frontends.

When more than one micro frontend accesses the same slice of state,
the state stops being an internal detail of one and becomes a means
of communication among several — with no declared contract, no
message and no import. The shape of that data becomes a de facto
public interface, and changing it breaks everyone who touches it at
the same time.

It applies to state libraries and to browser storage: a
`localStorage` key touched by several micro frontends is the same
thing as a store slice read by several.

A slice is identified by the library AND by the path. The `user`
key in `localStorage` and the `user` slice of a Redux store are
different data, and joining them by name would flag coupling that
does not exist.

The occurrence is SINGLE and binary: either the system uses global
state as a channel, or it does not. Emitting one per slice would say
the same thing several times — what matters is whether the practice
exists, and who takes part in it.
"""

from __future__ import annotations

from mfad.adapters.driven import i18n
from mfad.application.ports import Rule
from mfad.domain import (
    AntiPattern,
    AntiPatternDetection,
    MicroFrontendArchitecture,
    StateAccess,
)


def _slice(access: StateAccess) -> str:
    """`localStorage:token`, `react-redux:cart` — the same label as the edges."""

    return f"{access.library}:{access.path}"


class GlobalStateCommunication(Rule):

    anti_pattern = AntiPattern(
        name="global-state-communication",
        description=(
            "Global state accessed by more than one micro frontend, "
            "acting as an undeclared communication channel."
        ),
        category="Inter-frontend",
        reference="https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Global%20state%20communication",
    )

    def __init__(self, min_microfrontends: int = 2):

        #: Number of accessors from which the state stops being
        #: internal and becomes a channel. Two are enough.
        self.min_microfrontends = min_microfrontends

    def check(self, architecture: MicroFrontendArchitecture) -> list[AntiPatternDetection]:

        readers = self._readers(architecture)

        shared = {
            path: holders
            for path, holders in readers.items()
            if len(holders) >= self.min_microfrontends
        }

        if not shared:
            return []

        involved = sorted(
            {holder for holders in shared.values() for holder in holders}
        )

        text = {
            "dimension": i18n.ref("dimension.global_state"),
            "explanation": i18n.ref("gsc.explanation"),
            "message": i18n.ref(
                "gsc.message",
                n=len(involved),
                slices=len(shared),
                names=", ".join(self._short(item) for item in involved),
            ),
        }

        # Who is involved is already the row's column, and each slice,
        # with who reads, who writes and where, comes from `metadata.slices`.
        text["facts"] = [i18n.fact("fact.slices", len(shared))]

        return [
            AntiPatternDetection(
                anti_pattern=self.name,
                dimension=i18n.t(text["dimension"]),
                explanation=i18n.t(text["explanation"]),
                message=i18n.t(text["message"]),
                subjects=involved,
                locations=self._locations(architecture, shared),
                metadata={
                    "text": text,
                    "relation": "shared_state",
                    "edges": self._edges(shared),
                    "slices": {
                        path: sorted(holders)
                        for path, holders in sorted(shared.items())
                    },
                    "libraries": sorted(
                        {item.library for item in architecture.state_accesses}
                    ),
                },
            )
        ]

    @staticmethod
    def _readers(architecture: MicroFrontendArchitecture) -> dict[str, set[str]]:

        readers: dict[str, set[str]] = {}

        for access in architecture.state_accesses:
            readers.setdefault(_slice(access), set()).add(access.microfrontend)

        return readers

    @staticmethod
    def _edges(shared: dict[str, set[str]]) -> list[list[str]]:
        """
        The pairs that read the same slice, in both directions — the
        relation has no direction, and the drawing traces one arc per
        order.
        """

        pairs: list[list[str]] = []

        for holders in shared.values():

            ordered = sorted(holders)

            for source in ordered:
                for target in ordered:

                    if source != target and [source, target] not in pairs:
                        pairs.append([source, target])

        return pairs

    @staticmethod
    def _locations(architecture: MicroFrontendArchitecture, shared: dict) -> list:

        # A line may touch two slices; it appears only once.
        found: dict[tuple, object] = {}

        for access in architecture.state_accesses:

            if _slice(access) in shared:
                found.setdefault((access.at.file, access.at.line), access.at)

        return list(found.values())

    @staticmethod
    def _short(name: str) -> str:

        return name.rpartition("/")[2] or name
