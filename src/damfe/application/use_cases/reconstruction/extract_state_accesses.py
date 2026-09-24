"""Extrair o acesso ao estado global."""

from __future__ import annotations

from pathlib import Path

from damfe.application.errors import RepositoryNotFound
from damfe.application.ports import Reconstructor, UseCase
from damfe.application.results import StateAccessesResult
from damfe.domain import MicroFrontend


class ExtractStateAccessesUseCase(UseCase[StateAccessesResult]):

    def __init__(
        self,
        repository_path: Path,
        reconstructor: Reconstructor,
        microfrontends: list[MicroFrontend] | None = None,
    ):
        self.repository_path = repository_path
        self.reconstructor = reconstructor

        self.microfrontends = microfrontends

    def execute(self) -> StateAccessesResult:

        if not self.repository_path.exists():
            raise RepositoryNotFound(self.repository_path)

        microfrontends = self.microfrontends

        if microfrontends is None:
            microfrontends = self.reconstructor.microfrontends(
                self.repository_path
            )

        return StateAccessesResult(
            state_accesses=self.reconstructor.state_accesses(
                self.repository_path,
                microfrontends,
            )
        )
