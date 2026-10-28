"""
A micro frontend connected to almost all the others.

The symptom is a micro frontend that touches practically the whole
system — either because everyone depends on it, or because it
depends on everyone. In both cases it stops being an independently
deployable part and becomes the center of the system: any change to
it ripples everywhere, and it has to keep up with everyone's
evolution.

The connection is counted without direction. Depending on everyone
and being depended on by everyone are different problems — the
share of each goes into the metadata — but both characterize the
same excessive coupling.

Symmetric edges are left out. In the reconstruction, global state
becomes an edge between every pair that touches the same slice — a
token key read by everyone links everyone to everyone, and the rule
would flag almost the whole system for a coupling that has no
center. That coupling already has its own rule,
`global-state-communication`.
"""

from __future__ import annotations

from collections import defaultdict

from mfad.adapters.driven import i18n
from mfad.application.ports import Rule
from mfad.domain import AntiPattern, AntiPatternDetection, MicroFrontendArchitecture


class OneForAll(Rule):

    anti_pattern = AntiPattern(
        name="one-for-all",
        description=(
            "Micro frontend connected to almost all the others, by "
            "fragment, navigation or communication."
        ),
        category="Inter-frontend",
        reference="https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/One%20Micro%20Frontend%20for%20all",
    )

    def __init__(
        self,
        ratio: float = 0.9,
        min_microfrontends: int = 5,
    ):
        #: Fraction of the others the micro frontend must be
        #: connected to in order to be flagged.
        self.ratio = ratio

        #: System size floor. In a small system, being connected to
        #: all the others is normal, not a deviation — below this size
        #: the rule abstains instead of flagging everyone.
        self.min_microfrontends = min_microfrontends

    def check(self, architecture: MicroFrontendArchitecture) -> list[AntiPatternDetection]:

        # The orchestrator is excluded: reaching everyone is its job.
        # Keeping it in the computation would also inflate the degree
        # of all the others, since it navigates to the whole system.
        peers = [
            microfrontend.id
            for microfrontend in architecture.microfrontends
            if microfrontend.role != "shell"
        ]

        if len(peers) < self.min_microfrontends:
            return []

        known = set(peers)

        outgoing, incoming = self._degrees(architecture, known)

        detections: list[AntiPatternDetection] = []

        for peer in peers:

            others = len(known) - 1

            neighbours = (outgoing[peer] | incoming[peer]) - {peer}

            if len(neighbours) < self.ratio * others:
                continue

            detections.append(
                self._detection(
                    peer,
                    neighbours,
                    others,
                    outgoing[peer],
                    incoming[peer],
                )
            )

        return detections

    @staticmethod
    def _degrees(
        architecture: MicroFrontendArchitecture,
        known: set[str],
    ) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
        """Outgoing and incoming neighbours, joining the three relations."""

        outgoing: dict[str, set[str]] = defaultdict(set)
        incoming: dict[str, set[str]] = defaultdict(set)

        edges = (
            [
                (item.consumer, item.provider)
                for item in architecture.compositions
            ]
            + [
                (item.source, item.target)
                for item in architecture.navigations
            ]
            + [
                (item.source, item.target)
                for item in architecture.communications
                # The test is the property, not the mechanism, as in
                # cyclic-dependency.
                if item.directed
            ]
        )

        for source, target in edges:

            if source not in known or target not in known:
                continue

            outgoing[source].add(target)
            incoming[target].add(source)

        return outgoing, incoming

    def _detection(
        self,
        peer: str,
        neighbours: set[str],
        others: int,
        outgoing: set[str],
        incoming: set[str],
    ) -> AntiPatternDetection:

        text = {
            "dimension": i18n.ref("dimension.all_relations"),
            "explanation": i18n.ref("ofa.explanation"),
            "message": i18n.ref(
                "ofa.message",
                name=self._short(peer),
                neighbours=len(neighbours),
                others=others,
                out=len(outgoing),
                incoming=len(incoming),
            ),
        }

        text["facts"] = [
            i18n.fact("fact.connected", i18n.ref("fact.of", part=len(neighbours), whole=others)),
            i18n.fact("fact.depends_on", len(outgoing)),
            i18n.fact("fact.depended_by", len(incoming)),
        ]

        return AntiPatternDetection(
            anti_pattern=self.name,
            dimension=i18n.t(text["dimension"]),
            explanation=i18n.t(text["explanation"]),
            message=i18n.t(text["message"]),
            subjects=[peer, *sorted(neighbours)],
            metadata={
                "text": text,
                "edges": (
                    [[peer, other] for other in sorted(outgoing)]
                    + [[other, peer] for other in sorted(incoming)]
                ),
                "neighbours": len(neighbours),
                "others": others,
                "coverage": round(len(neighbours) / others, 2)
                if others
                else 0,
                "depends_on": sorted(outgoing),
                "depended_on_by": sorted(incoming),
            },
        )

    @staticmethod
    def _short(name: str) -> str:

        return name.rpartition("/")[2] or name
