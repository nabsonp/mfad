"""Module 2: detect anti-patterns over the artifacts."""

from __future__ import annotations

from pathlib import Path

from mfad.application.errors import ArtifactsNotFound, NoMicroFrontends
from mfad.application.ports import ArtifactRepository, Rule, UseCase
from mfad.application.results import DetectionResult
from mfad.domain import MicroFrontendArchitecture


class DetectUseCase(UseCase[DetectionResult]):

    def __init__(
        self,
        source: Path,
        destination: Path | None,
        rules: list[Rule],
        repository: ArtifactRepository,
        architecture: MicroFrontendArchitecture | None = None,
    ):
        self.source = source
        self.destination = destination
        self.rules = rules
        self.repository = repository

        # When chained, the artifacts are already in memory
        # and do not need to be read again from disk.
        self.architecture = architecture

    def execute(self) -> DetectionResult:

        architecture = self.architecture or self.repository.load(self.source)

        # An artifact read from disk and empty means a missing artifact;
        # coming chained from the reconstruction, it is a reconstruction
        # that found nothing, and the message has to say so.
        if not architecture.microfrontends:
            raise (
                NoMicroFrontends(self.source)
                if self.architecture is not None
                else ArtifactsNotFound(self.source)
            )

        detections = []

        for rule in self.rules:
            for detection in rule.check(architecture):
                # The occurrence carries the catalog reference: whoever reads it
                # without knowing the anti-pattern has somewhere to look up the definition.
                detection.reference = detection.reference or rule.anti_pattern.reference
                detections.append(detection)

        # Without severity, the order is the stable one: rule and message.
        detections.sort(key=lambda item: (item.anti_pattern, item.message))

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
