"""Extrair o consumo de fragmentos através das fronteiras."""

from __future__ import annotations

from pathlib import Path

from damfe.application.errors import RepositoryNotFound
from damfe.application.ports import Reconstructor, UseCase
from damfe.application.results import FragmentImportsResult
from damfe.domain import MicroFrontend


class ExtractFragmentImportsUseCase(UseCase[FragmentImportsResult]):

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

    def execute(self) -> FragmentImportsResult:

        if not self.repository_path.exists():
            raise RepositoryNotFound(self.repository_path)

        microfrontends = self.microfrontends

        if microfrontends is None:
            microfrontends = self.reconstructor.microfrontends(
                self.repository_path
            )

        return FragmentImportsResult(
            fragment_imports=self.reconstructor.fragment_imports(
                self.repository_path,
                microfrontends,
            )
        )
