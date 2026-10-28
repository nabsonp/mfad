"""
Setup moment: declare how the applications communicate.

Writes the specification that extraction will consult from then on.
Without arguments, it writes a commented template for the user to
fill in — it is the point where the human decision enters the
process, once, instead of on every analysis.
"""

from __future__ import annotations

from pathlib import Path

from mfad.application.ports import SpecRepository, UseCase
from mfad.application.results import CommunicationSetupResult
from mfad.domain import CommunicationSpec


class SetupCommunicationUseCase(UseCase[CommunicationSetupResult]):

    def __init__(
        self,
        destination: Path,
        specs: SpecRepository,
        spec: CommunicationSpec | None = None,
    ):
        self.destination = destination
        self.specs = specs
        self.spec = spec or CommunicationSpec()

    def execute(self) -> CommunicationSetupResult:

        written = self.specs.save_communication(
            self.spec,
            self.destination,
        )

        return CommunicationSetupResult(spec=self.spec, written=written)
