"""Extrair o inventário de aplicações de um repositório."""

from __future__ import annotations

from pathlib import Path

from mfad.application.errors import RepositoryNotFound
from mfad.application.ports import Reconstructor, UseCase
from mfad.application.results import MicroFrontendsResult


class ExtractMicroFrontendsUseCase(UseCase[MicroFrontendsResult]):

    def __init__(
        self,
        repository_path: Path,
        reconstructor: Reconstructor,
    ):
        self.repository_path = repository_path
        self.reconstructor = reconstructor

    def execute(self) -> MicroFrontendsResult:

        if not self.repository_path.exists():
            raise RepositoryNotFound(self.repository_path)

        return MicroFrontendsResult(
            microfrontends=self.reconstructor.microfrontends(
                self.repository_path
            )
        )
