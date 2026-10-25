"""Módulo 3: gerar a visualização da arquitetura e dos anti-padrões."""

from __future__ import annotations

from pathlib import Path

from mfad.application.errors import ArtifactsNotFound
from mfad.application.ports import ArtifactRepository, Renderer, UseCase
from mfad.application.results import VisualizationResult
from mfad.domain import MicroFrontendArchitecture, AntiPatternDetection


class VisualizeUseCase(UseCase[VisualizationResult]):

    def __init__(
        self,
        source: Path,
        destination: Path | None,
        renderer: Renderer,
        repository: ArtifactRepository,
        detections_path: Path | None = None,
        architecture: MicroFrontendArchitecture | None = None,
        detections: list[AntiPatternDetection] | None = None,
    ):
        self.source = source
        self.destination = destination
        self.renderer = renderer
        self.repository = repository
        self.detections_path = detections_path

        self.architecture = architecture
        self.detections = detections

    def execute(self) -> VisualizationResult:

        architecture = self.architecture or self.repository.load(self.source)

        if not architecture.microfrontends:
            raise ArtifactsNotFound(self.source)

        detections = self.detections

        if detections is None and self.detections_path:
            detections = self.repository.load_detections(self.detections_path)

        output = self.renderer.render(architecture, detections)

        written = None

        if self.destination:

            self.destination.parent.mkdir(parents=True, exist_ok=True)

            self.destination.write_text(output, encoding="utf-8")

            written = self.destination

        return VisualizationResult(output=output, written=written)
