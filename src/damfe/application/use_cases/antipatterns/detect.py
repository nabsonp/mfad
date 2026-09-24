"""Módulo 2: detectar anti-padrões sobre os artefatos."""

from __future__ import annotations

from pathlib import Path

from damfe.application.errors import ArtifactsNotFound
from damfe.application.ports import ArtifactRepository, Rule, UseCase
from damfe.application.results import DetectionResult
from damfe.domain import ArtifactSet


class DetectUseCase(UseCase[DetectionResult]):

    def __init__(
        self,
        source: Path,
        destination: Path | None,
        rules: list[Rule],
        repository: ArtifactRepository,
        artifacts: ArtifactSet | None = None,
    ):
        self.source = source
        self.destination = destination
        self.rules = rules
        self.repository = repository

        # Quando encadeado, os artefatos já estão em memória
        # e não precisam ser relidos do disco.
        self.artifacts = artifacts

    def execute(self) -> DetectionResult:

        artifacts = self.artifacts or self.repository.load(self.source)

        if not artifacts.microfrontends:
            raise ArtifactsNotFound(self.source)

        detections = [
            detection
            for rule in self.rules
            for detection in rule.check(artifacts)
        ]

        # Sem severidade, a ordem é a estável: regra e mensagem.
        detections.sort(key=lambda item: (item.rule, item.message))

        written = (
            self.repository.save_detections(detections, self.destination)
            if self.destination
            else None
        )

        return DetectionResult(
            detections=detections,
            rules_applied=len(self.rules),
            written=written,
        )
