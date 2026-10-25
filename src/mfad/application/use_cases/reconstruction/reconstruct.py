"""
Reconstrução completa: compõe os casos de uso de extração.

É o Command tirando proveito de si mesmo — um caso de uso cuja
execução é executar outros. A montagem do `MicroFrontendArchitecture` mora aqui,
na aplicação, e não no adaptador que extrai.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from mfad.application.ports import (
    ArtifactRepository,
    SourceProbe,
    UseCase,
)
from mfad.application.results import ReconstructionResult
from mfad.application.use_cases.reconstruction.extract_microfrontends import (
    ExtractMicroFrontendsUseCase,
)
from mfad.application.use_cases.reconstruction.extract_compositions import (
    ExtractCompositionsUseCase,
)
from mfad.application.use_cases.reconstruction.extract_api_calls import (
    ExtractApiCallsUseCase,
)
from mfad.application.use_cases.reconstruction.extract_communications import (
    ExtractCommunicationsUseCase,
)
from mfad.application.use_cases.reconstruction.extract_navigations import (
    ExtractNavigationsUseCase,
)
from mfad.application.use_cases.reconstruction.extract_state_accesses import (
    ExtractStateAccessesUseCase,
)
from mfad import __version__
from mfad.domain import MicroFrontendArchitecture, Provenance, edges_from_state
from mfad.domain.naming import by_directory, distinct


class ReconstructUseCase(UseCase[ReconstructionResult]):

    def __init__(
        self,
        repository_path: Path,
        destination: Path | None,
        extract_microfrontends: ExtractMicroFrontendsUseCase,
        extract_compositions: ExtractCompositionsUseCase,
        extract_navigations: ExtractNavigationsUseCase,
        extract_communications: ExtractCommunicationsUseCase,
        extract_api_calls: ExtractApiCallsUseCase,
        extract_state_accesses: ExtractStateAccessesUseCase,
        repository: ArtifactRepository,
        probe: SourceProbe,
        reconstructor_name: str = "",
    ):
        self.repository_path = repository_path
        self.destination = destination
        self.extract_microfrontends = extract_microfrontends
        self.extract_compositions = extract_compositions
        self.extract_navigations = extract_navigations
        self.extract_communications = extract_communications
        self.extract_api_calls = extract_api_calls
        self.extract_state_accesses = extract_state_accesses
        self.repository = repository
        self.probe = probe
        self.reconstructor_name = reconstructor_name

    def execute(self) -> ReconstructionResult:

        microfrontends = self.extract_microfrontends.execute().microfrontends

        distinct(microfrontends)

        self.extract_compositions.microfrontends = microfrontends

        compositions = (
            self.extract_compositions.execute().compositions
        )

        self.extract_navigations.microfrontends = microfrontends

        navigations = self.extract_navigations.execute().navigations

        self.extract_communications.microfrontends = microfrontends

        extracted = self.extract_communications.execute()

        communications = extracted.communications

        self.extract_api_calls.microfrontends = microfrontends

        api_calls = self.extract_api_calls.execute().api_calls

        self.extract_state_accesses.microfrontends = microfrontends

        state_accesses = (
            self.extract_state_accesses.execute().state_accesses
        )

        # O acoplamento por estado global entra no MESMO grafo das
        # demais comunicações. Ele é derivado aqui, na composição, e
        # não no extrator: o extrator de estado não conhece os outros
        # micro frontends, e a aresta só existe quando dois deles
        # leem a mesma fatia.
        communications = communications + edges_from_state(state_accesses)

        architecture = MicroFrontendArchitecture(
            project=self.repository_path.resolve().name,
            provenance=self._provenance(),
            microfrontends=microfrontends,
            compositions=compositions,
            navigations=navigations,
            communications=communications,
            api_calls=api_calls,
            state_accesses=state_accesses,
        )

        # Quem lê procura o micro frontend pelo repositório, não pelo
        # nome com que ele é registrado.
        by_directory(architecture)

        written = (
            self.repository.save(architecture, self.destination)
            if self.destination
            else []
        )

        return ReconstructionResult(
            architecture=architecture,
            written=written,
            unmatched=extracted.unmatched,
        )

    def _provenance(self) -> Provenance:
        """
        O carimbo da execução.

        A revisão de cada repositório é o que torna o resultado
        reproduzível: sem ela, um conjunto de artefatos não diz
        sobre QUAL versão do código ele fala, e deixa de ser
        verificável assim que o repositório recebe um commit.
        """

        return Provenance(
            tool=__version__,
            generated_at=datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            reconstructor=self.reconstructor_name,
            sources=self.probe.describe(self.repository_path),
        )
