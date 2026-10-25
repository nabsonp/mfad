"""Módulo 2: detectar anti-padrões sobre os artefatos."""

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

        # Quando encadeado, os artefatos já estão em memória
        # e não precisam ser relidos do disco.
        self.architecture = architecture

    def execute(self) -> DetectionResult:

        architecture = self.architecture or self.repository.load(self.source)

        # Artefato lido do disco e vazio é falta de artefato; vindo
        # encadeado da reconstrução, é reconstrução que não achou nada,
        # e a mensagem tem de dizer isso.
        if not architecture.microfrontends:
            raise (
                NoMicroFrontends(self.source)
                if self.architecture is not None
                else ArtifactsNotFound(self.source)
            )

        detections = []

        for rule in self.rules:
            for detection in rule.check(architecture):
                # A ocorrência leva a referência do catálogo: quem a lê
                # sem conhecer o anti-padrão tem onde consultar a definição.
                detection.reference = detection.reference or rule.anti_pattern.reference
                detections.append(detection)

        # Sem severidade, a ordem é a estável: regra e mensagem.
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
