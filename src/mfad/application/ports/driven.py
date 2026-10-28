"""
Driven ports — the right side of the hexagon.

They define what the application needs from the outside world. They
are implemented by the driven adapters (`adapters/driven`): the
single-spa extractor, the JSON storage, and so on. The application
depends on these abstractions, never on them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from mfad.domain import (
    MicroFrontend,
    MicroFrontendArchitecture,
    Communication,
    CommunicationSpec,
    AntiPattern,
    AntiPatternDetection,
    Composition,
    Navigation,
    SourceRepository,
)


class Reconstructor(ABC):
    """
    Extracts architectural artifacts from a repository.

    One implementation per micro frontend technology.

    The port is segmented by artifact TYPE, not into a single
    operation: whoever only wants the application inventory does not
    pay for extracting the imports. Each method is a step that a use
    case can trigger on its own.
    """

    #: identifier used in the CLI, e.g.: "single-spa"
    name: str = ""

    #: short description
    description: str = ""

    @abstractmethod
    def detect(self, repository: Path) -> bool:
        """Tells whether this reconstructor recognizes the repository."""

    @abstractmethod
    def microfrontends(self, repository: Path) -> list[MicroFrontend]:
        """The deployment units and what each one contains."""

    @abstractmethod
    def compositions(
        self,
        repository: Path,
        microfrontends: list[MicroFrontend],
    ) -> list[Composition]:
        """
        The consumption of fragments across boundaries.

        Receives the already extracted applications because it is
        their catalog that tells a fragment apart from any export.
        """

    @abstractmethod
    def navigations(
        self,
        repository: Path,
        microfrontends: list[MicroFrontend],
    ) -> list[Navigation]:
        """
        The navigations that cross the boundary between applications.

        Receives the already extracted applications because it is the
        routes they declare that say who owns each destination.
        """

    @abstractmethod
    def communications(
        self,
        repository: Path,
        microfrontends: list[MicroFrontend],
        spec: CommunicationSpec,
    ) -> list[Communication]:
        """
        The message exchange between applications.

        Depends on the `spec`: with no declared mechanism there is
        nothing to look for, and the result is empty. It is the only
        extraction that needs configuration, because it is the only
        one without a standard contract in the ecosystem.
        """


class SourceProbe(ABC):
    """
    Identifies the revision of each analyzed repository.

    It exists so that provenance is the responsibility of an
    adapter: reading the git state is I/O, and the use case only
    needs the result. An implementation that finds no git at all
    returns an empty list — the analysis does not depend on this.
    """

    @abstractmethod
    def describe(self, root: Path) -> list[SourceRepository]:
        """The repositories under `root`, in stable order."""


class Rule(ABC):
    """
    How to look for an anti-pattern in the artifacts.

    The rule is the HOW; the `AntiPattern` it declares is the WHAT.
    They are separate because the same catalog entry admits more than
    one operationalization, and switching operationalization does not
    change what the anti-pattern is.

    Operates only on the domain model — which is why detection is
    agnostic to the source technology.
    """

    #: the catalog entry this rule looks for
    anti_pattern: AntiPattern

    @property
    def name(self) -> str:
        return self.anti_pattern.name

    @property
    def description(self) -> str:
        return self.anti_pattern.description

    @abstractmethod
    def check(self, architecture: MicroFrontendArchitecture) -> list[AntiPatternDetection]:
        """Evaluates the artifacts and returns the occurrences."""


class Renderer(ABC):
    """Serializes artifacts and anti-patterns into some visual format."""

    #: identifier used in the CLI, e.g.: "mermaid"
    name: str = ""

    #: suggested extension for the output file
    extension: str = "txt"

    @abstractmethod
    def render(
        self,
        architecture: MicroFrontendArchitecture,
        detections: list[AntiPatternDetection] | None = None,
    ) -> str:
        """Returns the representation as text."""


class SpecRepository(ABC):
    """
    Reading and writing of the communication declaration.

    Separate from `ArtifactRepository` because the spec is an INPUT
    of the analysis, written once at setup, while the artifacts are
    output, rewritten on every run.
    """

    @abstractmethod
    def load_communication(self, source: Path) -> CommunicationSpec:
        ...

    @abstractmethod
    def save_communication(
        self,
        spec: CommunicationSpec,
        destination: Path,
    ) -> Path:
        ...


class ArtifactRepository(ABC):
    """
    Persistence of artifacts and anti-patterns.

    Abstracted so that the use cases know neither the format nor the
    storage medium.
    """

    @abstractmethod
    def save(
        self,
        architecture: MicroFrontendArchitecture,
        destination: Path,
    ) -> list[Path]:
        ...

    @abstractmethod
    def load(self, source: Path) -> MicroFrontendArchitecture:
        ...

    @abstractmethod
    def save_detections(
        self,
        detections: list[AntiPatternDetection],
        destination: Path,
    ) -> Path:
        ...

    @abstractmethod
    def load_detections(self, source: Path) -> list[AntiPatternDetection]:
        ...
