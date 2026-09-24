"""
Reconstrução completa: compõe os casos de uso de extração.

É o Command tirando proveito de si mesmo — um caso de uso cuja
execução é executar outros. A montagem do `ArtifactSet` mora aqui,
na aplicação, e não no adaptador que extrai.
"""

from __future__ import annotations

from pathlib import Path

from damfe.application.ports import ArtifactRepository, UseCase
from damfe.application.results import ReconstructionResult
from damfe.application.use_cases.reconstruction.extract_microfrontends import (
    ExtractMicroFrontendsUseCase,
)
from damfe.application.use_cases.reconstruction.extract_fragment_imports import (
    ExtractFragmentImportsUseCase,
)
from damfe.application.use_cases.reconstruction.extract_api_calls import (
    ExtractApiCallsUseCase,
)
from damfe.application.use_cases.reconstruction.extract_communications import (
    ExtractCommunicationsUseCase,
)
from damfe.application.use_cases.reconstruction.extract_navigations import (
    ExtractNavigationsUseCase,
)
from damfe.application.use_cases.reconstruction.resolve_domains import (
    ResolveDomainsUseCase,
)
from damfe.application.use_cases.reconstruction.extract_state_accesses import (
    ExtractStateAccessesUseCase,
)
from damfe.domain import ArtifactSet, edges_from_state


class ReconstructUseCase(UseCase[ReconstructionResult]):

    def __init__(
        self,
        repository_path: Path,
        destination: Path | None,
        extract_microfrontends: ExtractMicroFrontendsUseCase,
        extract_fragment_imports: ExtractFragmentImportsUseCase,
        extract_navigations: ExtractNavigationsUseCase,
        extract_communications: ExtractCommunicationsUseCase,
        extract_api_calls: ExtractApiCallsUseCase,
        extract_state_accesses: ExtractStateAccessesUseCase,
        resolve_domains: ResolveDomainsUseCase,
        repository: ArtifactRepository,
    ):
        self.repository_path = repository_path
        self.destination = destination
        self.extract_microfrontends = extract_microfrontends
        self.extract_fragment_imports = extract_fragment_imports
        self.extract_navigations = extract_navigations
        self.extract_communications = extract_communications
        self.extract_api_calls = extract_api_calls
        self.extract_state_accesses = extract_state_accesses
        self.resolve_domains = resolve_domains
        self.repository = repository

    def execute(self) -> ReconstructionResult:

        microfrontends = self.extract_microfrontends.execute().microfrontends

        self.extract_fragment_imports.microfrontends = microfrontends

        fragment_imports = (
            self.extract_fragment_imports.execute().fragment_imports
        )

        self.extract_navigations.microfrontends = microfrontends

        navigations = self.extract_navigations.execute().navigations

        self.extract_communications.microfrontends = microfrontends

        communications = (
            self.extract_communications.execute().communications
        )

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

        artifacts = ArtifactSet(
            project=self.repository_path.resolve().name,
            microfrontends=microfrontends,
            fragment_imports=fragment_imports,
            navigations=navigations,
            communications=communications,
            api_calls=api_calls,
            state_accesses=state_accesses,
        )

        # Os domínios são resolvidos por último: dependem de tudo
        # que foi extraído antes.
        self.resolve_domains.artifacts = artifacts

        artifacts.domains = self.resolve_domains.execute().domains

        written = (
            self.repository.save(artifacts, self.destination)
            if self.destination
            else []
        )

        return ReconstructionResult(artifacts=artifacts, written=written)
