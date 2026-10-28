"""The catalog anti-pattern and its occurrences — neutral like the rest."""

from __future__ import annotations

from dataclasses import dataclass, field

from mfad.domain.model import SourceLocation


@dataclass(frozen=True)
class AntiPattern:
    """
    An entry of the anti-pattern catalog.

    It exists independently of any analysis: `cyclic-dependency` is
    an anti-pattern described in the literature, whether or not it
    has been found in some system. It is the WHAT.

    Distinct from `Rule`, which is the HOW — the port that knows how
    to look for it in the artifacts. The same catalog entry could
    have more than one operationalization, and none of them changes
    what the anti-pattern is.

    And distinct from `AntiPatternDetection`, which is an occurrence:
    this is the type, that is the instance.
    """

    #: stable identifier, e.g.: "cyclic-dependency"
    name: str

    description: str

    #: the category of the source catalog
    category: str = ""

    #: where the anti-pattern is described
    reference: str = ""


@dataclass
class AntiPatternDetection:
    """
    An anti-pattern occurrence.

    Deliberately WITHOUT severity. Assigning "high" or "low" to an
    anti-pattern would require a defined and justified scale, and
    inventing one would give the air of a measurement to what would
    be opinion. What the occurrence reports instead is `dimension`:
    which architectural relation produced it — because a composition
    cycle and a navigation cycle are different anti-patterns, and
    that difference is observable in the artifacts, not arbitrated.

    `subjects` holds the identifiers involved, and `metadata` what is
    specific to each rule, so that the presentation can represent
    each anti-pattern without knowing it.

    `anti_pattern` is the NAME of the catalog entry, not the object —
    like every reference in this model.
    """

    anti_pattern: str
    message: str
    dimension: str = ""
    explanation: str = ""
    subjects: list[str] = field(default_factory=list)
    locations: list[SourceLocation] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    #: where the anti-pattern is described in the catalog: the definition
    #: for whoever evaluates the occurrence without knowing it
    reference: str = ""
