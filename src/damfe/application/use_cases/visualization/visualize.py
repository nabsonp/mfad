"""Módulo 3: gerar a visualização da arquitetura e dos anti-padrões."""

from __future__ import annotations

from pathlib import Path

from damfe.application.errors import ArtifactsNotFound
from damfe.application.ports import ArtifactRepository, Renderer, UseCase
from damfe.application.results import VisualizationResult
from damfe.domain import ArtifactSet, AntiPatternDetection


class VisualizeUseCase(UseCase[VisualizationResult]):

    def __init__(
        self,
        source: Path,
        destination: Path | None,
        renderer: Renderer,
        repository: ArtifactRepository,
        detections_path: Path | None = None,
        artifacts: ArtifactSet | None = None,
        detections: list[AntiPatternDetection] | None = None,
    ):
        self.source = source
        self.destination = destination
        self.renderer = renderer
        self.repository = repository
        self.detections_path = detections_path

        self.artifacts = artifacts
        self.detections = detections

    def execute(self) -> VisualizationResult:

        artifacts = self.artifacts or self.repository.load(self.source)

        if not artifacts.microfrontends:
            raise ArtifactsNotFound(self.source)

        detections = self.detections

        if detections is None and self.detections_path:
            detections = self.repository.load_detections(self.detections_path)

        output = self.renderer.render(artifacts, detections)

        written = None

        if self.destination:

            self.destination.parent.mkdir(parents=True, exist_ok=True)

            self.destination.write_text(output, encoding="utf-8")

            written = self.destination

        return VisualizationResult(output=output, written=written)
