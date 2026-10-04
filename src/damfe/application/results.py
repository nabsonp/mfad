"""
Resultados dos casos de uso.

Dados, não texto: o adaptador condutor decide como apresentá-los.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from damfe.domain import (
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

    #: Mecanismos declarados que não produziram aresta nenhuma.
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

    #: Mecanismos declarados que não produziram aresta nenhuma.
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
