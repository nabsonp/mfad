"""
Momento de setup: declarar como as aplicações se comunicam.

Grava a especificação que a extração vai consultar dali em diante.
Sem argumentos, escreve um modelo comentado para o usuário
preencher — é o ponto em que a decisão humana entra no processo,
uma vez só, em vez de a cada análise.
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
