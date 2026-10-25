"""Extrair o consumo de fragmentos através das fronteiras."""

from __future__ import annotations

from pathlib import Path

from mfad.application.errors import RepositoryNotFound
from mfad.application.ports import Reconstructor, UseCase
from mfad.application.results import CompositionsResult
from mfad.domain import MicroFrontend


class ExtractCompositionsUseCase(UseCase[CompositionsResult]):

    def __init__(
        self,
        repository_path: Path,
        reconstructor: Reconstructor,
        microfrontends: list[MicroFrontend] | None = None,
    ):
        self.repository_path = repository_path
        self.reconstructor = reconstructor

        # Quando já foram extraídas, não se extrai de novo.
        self.microfrontends = microfrontends

    def execute(self) -> CompositionsResult:

        if not self.repository_path.exists():
            raise RepositoryNotFound(self.repository_path)

        microfrontends = self.microfrontends

        if microfrontends is None:
            microfrontends = self.reconstructor.microfrontends(
                self.repository_path
            )

        return CompositionsResult(
            compositions=self.reconstructor.compositions(
                self.repository_path,
                microfrontends,
            )
        )
