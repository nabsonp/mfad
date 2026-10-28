"""
Micro frontend too small to stand on its own as a unit.

The catalog describes excessive fragmentation: the unit is so small
that the cost of keeping it separate outweighs the gain.

Two criteria combined with OR. The FLOOR is absolute and depends on
no neighbour: below it the unit delivers too little to be a micro
frontend. The OUTLIER is the lower Tukey fence over the system's own
distribution, and only applies when there is a distribution to
measure.

Both also require CODE below the system median. Screens and
fragments count where the unit is seen, not how much it does: an
Angular application with two routes and dozens of tabs and dialogs
has few screens and is among the largest in the system. It is the
same double requirement as `mega-frontend`, from the opposite side —
few screens with a lot of code is not a small unit, it is a dense
screen.
"""

from __future__ import annotations

import statistics

from mfad.adapters.driven import i18n
from mfad.adapters.driven.antipatterns.alignment import (
    Sizes,
    fences,
    peers,
)
from mfad.application.ports import Rule
from mfad.domain import AntiPattern, AntiPatternDetection, MicroFrontendArchitecture


class NanoFrontend(Rule):

    anti_pattern = AntiPattern(
        name="nano-frontend",
        description=(
            "Micro frontend too small to stand on its own as a "
            "deployment unit."
        ),
        category="Intra-frontend",
        reference="https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Nano%20Frontend",
    )

    def __init__(self, floor: int = 5):

        #: Absolute floor of screens plus fragments.
        #:
        #: A declared choice, not a measured one. On the two reference
        #: systems it flags 9 of the 10 units, and it still needs
        #: calibration against the study dataset.
        self.floor = floor

    def check(
        self,
        architecture: MicroFrontendArchitecture,
    ) -> list[AntiPatternDetection]:

        candidates = peers(architecture)

        sizes = Sizes.of(candidates)

        measured = {
            item.id: len(item.screens) + len(item.fragments)
            for item in candidates
            # An extraction that did not resolve the entrypoint returns
            # zero for everything, and would enter the distribution
            # pulling it down besides being flagged. A reading failure
            # is not an anti-pattern.
            if item.metadata.get("entrypoint_resolved") is not False
        }

        limit = fences(list(measured.values()))

        lines = sorted(
            item.size.code_lines
            for item in candidates
            if item.id in measured
        )

        median_lines = statistics.median(lines) if lines else 0

        found: list[AntiPatternDetection] = []

        for microfrontend in candidates:

            size = measured.get(microfrontend.id)

            if size is None:
                continue

            # More code than half of the peers is not a small unit.
            if microfrontend.size.code_lines >= median_lines:
                continue

            if size <= self.floor:
                criterion, threshold = "nano.criterion.floor", float(self.floor)

            elif limit and size < limit.low:
                criterion, threshold = "nano.criterion.outlier", limit.low

            else:
                continue

            found.append(
                self._detection(
                    microfrontend, size, criterion, threshold, limit, sizes,
                    median_lines,
                )
            )

        return found

    def _detection(
        self,
        microfrontend,
        size: int,
        criterion: str,
        threshold: float,
        limit,
        sizes,
        median_lines: float,
    ) -> AntiPatternDetection:

        screens = len(microfrontend.screens)
        fragments = len(microfrontend.fragments)

        text = {
            "dimension": i18n.ref("dimension.size"),
            "explanation": i18n.ref("nano.explanation"),
            "message": i18n.ref(
                "nano.message",
                name=self._short(microfrontend.id),
                screens=screens,
                fragments=fragments,
                size=size,
                threshold=f"{threshold:g}",
                criterion=i18n.ref(criterion),
                lines=microfrontend.size.code_lines,
                median=f"{median_lines:g}",
            ),
        }

        text["facts"] = [
            i18n.fact("fact.screens", screens),
            i18n.fact("fact.fragments", fragments),
            i18n.fact("fact.size", size),
            i18n.fact("fact.size_limit", i18n.ref("fact.limit_by", value=f"{threshold:g}", criterion=i18n.ref(criterion))),
            i18n.fact("fact.code_lines", microfrontend.size.code_lines),
            i18n.fact("fact.median_lines", f"{median_lines:g}"),
        ]

        return AntiPatternDetection(
            anti_pattern=self.name,
            dimension=i18n.t(text["dimension"]),
            explanation=i18n.t(text["explanation"]),
            message=i18n.t(text["message"]),
            subjects=[microfrontend.id],
            metadata={
                "text": text,
                "criterion": i18n.t(criterion),
                "threshold": threshold,
                "screens": screens,
                "fragments": fragments,
                "lines": microfrontend.size.code_lines,
                "floor": self.floor,
                "median_screens": sizes.screens,
                "median_fragments": sizes.fragments,
                "median_lines": median_lines,
                **(
                    {"q1": limit.q1, "q3": limit.q3, "iqr": limit.iqr}
                    if limit
                    else {"distribution": "insufficient sample"}
                ),
            },
        )

    @staticmethod
    def _short(name: str) -> str:

        return name.rpartition("/")[2] or name
