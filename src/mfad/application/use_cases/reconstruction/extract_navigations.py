"""Extract the navigations that cross the boundary between applications."""

from __future__ import annotations

from pathlib import Path

from mfad.application.errors import RepositoryNotFound
from mfad.application.ports import Reconstructor, UseCase
from mfad.application.results import NavigationsResult
from mfad.domain import MicroFrontend


class ExtractNavigationsUseCase(UseCase[NavigationsResult]):

    def __init__(
        self,
        repository_path: Path,
        reconstructor: Reconstructor,
        microfrontends: list[MicroFrontend] | None = None,
    ):
        self.repository_path = repository_path
        self.reconstructor = reconstructor

        # When already extracted, they are not extracted again.
        self.microfrontends = microfrontends

    def execute(self) -> NavigationsResult:

        if not self.repository_path.exists():
            raise RepositoryNotFound(self.repository_path)

        microfrontends = self.microfrontends

        if microfrontends is None:
            microfrontends = self.reconstructor.microfrontends(
                self.repository_path
            )

        return NavigationsResult(
            navigations=self.reconstructor.navigations(
                self.repository_path,
                microfrontends,
            )
        )
