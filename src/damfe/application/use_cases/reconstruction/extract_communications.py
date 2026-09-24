"""Extrair a comunicação declarada entre aplicações."""

from __future__ import annotations

from pathlib import Path

from damfe.application.errors import RepositoryNotFound
from damfe.application.ports import Reconstructor, SpecRepository, UseCase
from damfe.application.results import CommunicationsResult
from damfe.domain import MicroFrontend


class ExtractCommunicationsUseCase(UseCase[CommunicationsResult]):

    def __init__(
        self,
        repository_path: Path,
        spec_path: Path,
        reconstructor: Reconstructor,
        specs: SpecRepository,
        microfrontends: list[MicroFrontend] | None = None,
    ):
        self.repository_path = repository_path
        self.spec_path = spec_path
        self.reconstructor = reconstructor
        self.specs = specs

        self.microfrontends = microfrontends

    def execute(self) -> CommunicationsResult:

        if not self.repository_path.exists():
            raise RepositoryNotFound(self.repository_path)

        spec = self.specs.load_communication(self.spec_path)

        # A extração acontece com ou sem declaração: as primitivas
        # da plataforma e os barramentos conhecidos não dependem
        # dela. O `configured` só informa se há declaração, para
        # que a apresentação possa dizer o que ficou de fora.
        microfrontends = self.microfrontends

        if microfrontends is None:
            microfrontends = self.reconstructor.microfrontends(
                self.repository_path
            )

        return CommunicationsResult(
            communications=self.reconstructor.communications(
                self.repository_path,
                microfrontends,
                spec,
            ),
            configured=bool(spec),
        )
