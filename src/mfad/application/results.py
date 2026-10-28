"""
Use-case results.

Data, not text: the driving adapter decides how to present them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from mfad.domain import (
    ApiCall,
    MicroFrontend,
    MicroFrontendArchitecture,
    Communication,
    CommunicationSpec,
    AntiPatternDetection,
    Composition,
    Navigation,
    StateAccess,
)


@dataclass
class MicroFrontendsResult:
    microfrontends: list[MicroFrontend]


@dataclass
class CompositionsResult:
    compositions: list[Composition]


@dataclass
class ApiCallsResult:
    api_calls: list[ApiCall]


@dataclass
class CommunicationsResult:
    communications: list[Communication]
    configured: bool

    #: Declared mechanisms that produced no edge at all.
    unmatched: list[str] = field(default_factory=list)


@dataclass
class CommunicationSetupResult:
    spec: CommunicationSpec
    written: Path


@dataclass
class StateAccessesResult:
    state_accesses: list[StateAccess]


@dataclass
class NavigationsResult:
    navigations: list[Navigation]


@dataclass
class ReconstructionResult:
    architecture: MicroFrontendArchitecture
    written: list[Path] = field(default_factory=list)

    #: Declared mechanisms that produced no edge at all.
    unmatched: list[str] = field(default_factory=list)


@dataclass
class DetectionResult:
    detections: list[AntiPatternDetection]
    rules_applied: int
    written: Path | None = None


@dataclass
class VisualizationResult:
    output: str
    written: Path | None = None
