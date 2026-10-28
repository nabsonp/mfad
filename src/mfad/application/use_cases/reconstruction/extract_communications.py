"""Extract the declared communication between applications."""

from __future__ import annotations

from pathlib import Path

from mfad.application.errors import RepositoryNotFound
from mfad.application.ports import Reconstructor, SpecRepository, UseCase
from mfad.application.results import CommunicationsResult
from mfad.domain import MicroFrontend


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

        # Extraction happens with or without a declaration: the
        # platform primitives and the known buses do not depend on
        # it. `configured` only tells whether there is a declaration,
        # so that the presentation can say what was left out.
        microfrontends = self.microfrontends

        if microfrontends is None:
            microfrontends = self.reconstructor.microfrontends(
                self.repository_path
            )

        communications = self.reconstructor.communications(
            self.repository_path,
            microfrontends,
            spec,
        )

        return CommunicationsResult(
            communications=communications,
            configured=bool(spec),
            unmatched=self._unmatched(spec, communications),
        )

    @staticmethod
    def _unmatched(spec, communications) -> list[str]:
        """
        Declared mechanisms that yielded no edge at all.

        A declaration whose `module` does not match the actual import
        specifier silently produces zero, and zero is a plausible
        result — the system may really not use that channel. Without
        this warning, a typo and a genuine absence are
        indistinguishable.
        """

        found = {item.mechanism for item in communications}

        return [
            mechanism.name
            for mechanism in spec.mechanisms
            if mechanism.name not in found
        ]
