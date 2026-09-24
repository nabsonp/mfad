"""
Resultados dos casos de uso.

Dados, não texto: o adaptador condutor decide como apresentá-los.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from damfe.application.settings import LlmSettings
from damfe.domain import (
    ApiCall,
    Domain,
    MicroFrontend,
    ArtifactSet,
    Communication,
    CommunicationSpec,
    AntiPatternDetection,
    FragmentImport,
    Navigation,
    StateAccess,
)


@dataclass
class MicroFrontendsResult:
    microfrontends: list[MicroFrontend]


@dataclass
class FragmentImportsResult:
    fragment_imports: list[FragmentImport]


@dataclass
class ApiCallsResult:
    api_calls: list[ApiCall]


@dataclass
class CommunicationsResult:
    communications: list[Communication]
    configured: bool


@dataclass
class CommunicationSetupResult:
    spec: CommunicationSpec
    written: Path


@dataclass
class StateAccessesResult:
    state_accesses: list[StateAccess]


@dataclass
class DomainsResult:
    domains: list[Domain]
    declared: bool


@dataclass
class NavigationsResult:
    navigations: list[Navigation]


@dataclass
class ReconstructionResult:
    artifacts: ArtifactSet
    written: list[Path] = field(default_factory=list)


@dataclass
class DetectionResult:
    detections: list[AntiPatternDetection]
    rules_applied: int
    written: Path | None = None


@dataclass
class LlmSetupResult:
    settings: LlmSettings
    written: Path | None


@dataclass
class VisualizationResult:
    output: str
    written: Path | None = None
