"""
The system size measure, shared by the granularity rules.

`nano-frontend` and `mega-frontend` ask the same question from
opposite sides: is this unit too small or too large compared to the
others? The comparison is relative on purpose — "few screens"
depends on the size of the neighbours, and an absolute threshold
would be a number chosen without justification.

The cut is the TUKEY FENCE, `Q1 - 1.5 x IQR` and `Q3 + 1.5 x IQR`,
which is the standard definition of an outlier in descriptive
statistics. It used to be multiples of the median chosen for
symmetry — 0.4 and 2.0 — with no origin at all. The fence has a
name, a reference and a property that a median multiple lacks: on a
homogeneous set it flags no one, instead of flagging a fixed
fraction.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from mfad.domain import MicroFrontendArchitecture, MicroFrontend


@dataclass
class Sizes:
    """The system medians, in screens, fragments and lines."""

    screens: float
    fragments: float
    code_lines: float

    @property
    def measurable(self) -> bool:
        """
        Whether there is a measure to compare against.

        A zero median does not mean "everyone is small": it means
        nothing was measured. Comparing against it makes any fraction
        true — `0 < 0.4 × 0` — and the rule flags every micro
        frontend at once, which is exactly the result an empty
        extraction produces.

        When the reconstruction finds neither screens nor fragments,
        the right thing is for the rule to abstain and the report to
        say data was missing, not to invent an anomaly for each unit.
        """

        return self.screens > 0 or self.fragments > 0

    @classmethod
    def of(cls, microfrontends: list[MicroFrontend]) -> "Sizes":

        if not microfrontends:
            return cls(screens=0, fragments=0, code_lines=0)

        return cls(
            screens=statistics.median(
                len(item.screens) for item in microfrontends
            ),
            fragments=statistics.median(
                len(item.fragments) for item in microfrontends
            ),
            code_lines=statistics.median(
                item.size.code_lines for item in microfrontends
            ),
        )


def peers(architecture: MicroFrontendArchitecture) -> list[MicroFrontend]:
    """
    The micro frontends that take part in the comparison.

    The orchestrator is left out: it exists to host the others, and
    comparing its size with theirs measures the wrong thing.
    """

    return [
        item
        for item in architecture.microfrontends
        if item.role != "shell"
    ]


#: Minimum number of units for a quartile to mean anything.
#:
#: With four points the interpolation invents fractional values over
#: a sample of integers, and the quartile becomes fiction. Below this
#: the rule abstains: "system too small to talk about outliers" is a
#: better answer than an invented number.
MIN_SAMPLE = 8

#: Tukey's classic multiplier.
WHISKER = 1.5


@dataclass(frozen=True)
class Fences:
    """The lower and upper fences of a distribution."""

    low: float
    high: float
    q1: float
    q3: float
    iqr: float


def fences(
    values: list[float],
    min_sample: int = MIN_SAMPLE,
) -> Fences | None:
    """
    The Tukey fences, or `None` when there is nothing to measure.

    A single abstention: a sample smaller than `min_sample`, where the
    quartile describes no distribution at all.

    A zero IQR does NOT abstain. The distribution is constant, both
    fences collapse onto the same point, and then any deviation is an
    outlier — which is consistent, because with zero spread any
    difference lies at an infinite distance in IQRs. Callers compare
    against the fence with a STRICT inequality, so the degenerate case
    resolves itself: units sitting on the point are not flagged, and
    only the ones that stand out are. Abstaining here hid the most
    obvious outlier there is — nine equal units and one seven times
    larger.
    """

    if len(values) < min_sample:
        return None

    q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")

    iqr = q3 - q1

    return Fences(
        low=q1 - WHISKER * iqr,
        high=q3 + WHISKER * iqr,
        q1=q1,
        q3=q3,
        iqr=iqr,
    )
