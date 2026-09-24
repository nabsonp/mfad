"""
Composition root.

Único lugar do sistema que conhece implementações concretas. É
aqui que os registros são populados e que os casos de uso recebem
suas dependências injetadas. Todo o resto fala só com as portas
de `damfe.application.ports`.
"""

from __future__ import annotations

from pathlib import Path

from damfe.adapters.driven import antipatterns, reconstruction, visualization
from damfe.adapters.driven.antipatterns.rules import (
    AccessToDifferentDomains,
    CyclicDependency,
    GlobalStateCommunication,
    HammeringApis,
    HubLikeDependency,
    MegaFrontend,
    NanoFrontend,
    OneForAll,
)
from damfe.adapters.driven.reconstruction.singlespa.reconstructor import (
    SingleSpaReconstructor,
)
from damfe.adapters.driven.reconstruction.modulefederation import (
    ModuleFederationReconstructor,
)
from damfe.adapters.driven.visualization.features import FeaturesRenderer
from damfe.adapters.driven.visualization.html import HtmlRenderer
from damfe.adapters.driven.storage import (
    FileSettingsRepository,
    JsonArtifactRepository,
    YamlSpecRepository,
)
from damfe.application.ports import (
    ArtifactRepository,
    Reconstructor,
    Rule,
    SettingsRepository,
    SpecRepository,
)
from damfe.application.use_cases import (
    ExtractApiCallsUseCase,
    DetectUseCase,
    ExtractMicroFrontendsUseCase,
    ExtractCommunicationsUseCase,
    ExtractFragmentImportsUseCase,
    ExtractNavigationsUseCase,
    ExtractStateAccessesUseCase,
    ReconstructUseCase,
    ResolveDomainsUseCase,
    SetupLlmUseCase,
    SetupCommunicationUseCase,
    VisualizeUseCase,
)


def bootstrap() -> None:
    """Popula os registros com o que vem de fábrica."""

    if reconstruction.available():
        return

    reconstruction.register(SingleSpaReconstructor())
    reconstruction.register(ModuleFederationReconstructor())

    antipatterns.register(AccessToDifferentDomains())
    antipatterns.register(CyclicDependency())
    antipatterns.register(GlobalStateCommunication())
    antipatterns.register(HammeringApis())
    antipatterns.register(HubLikeDependency())
    antipatterns.register(MegaFrontend())
    antipatterns.register(NanoFrontend())
    antipatterns.register(OneForAll())

    visualization.register(HtmlRenderer())
    visualization.register(FeaturesRenderer())


class Container:
    """Fábrica de casos de uso com as dependências resolvidas."""

    def __init__(self):

        bootstrap()

        self.repository: ArtifactRepository = JsonArtifactRepository()

        self.specs: SpecRepository = YamlSpecRepository()

        self.settings: SettingsRepository = FileSettingsRepository()

    # ------------------------------------------------------------------
    # Resolução de implementações
    # ------------------------------------------------------------------

    def reconstructor(
        self,
        framework: str | None,
        repository_path: Path,
        organization_prefix: str | None = None,
    ) -> Reconstructor | None:

        if framework:
            chosen = reconstruction.get(framework)

        else:
            chosen = reconstruction.detect(repository_path)

            if not chosen:
                return None

        # O prefixo é opcional e específico de quem o suporta.
        if organization_prefix and hasattr(chosen, "organization_prefix"):
            chosen.organization_prefix = organization_prefix

        return chosen

    def rules(self, names: list[str] | None) -> list[Rule]:

        if not names:
            return antipatterns.available()

        return [antipatterns.get(name) for name in names]

    # ------------------------------------------------------------------
    # Casos de uso
    # ------------------------------------------------------------------

    def extract_microfrontends(
        self,
        repository_path: Path,
        reconstructor: Reconstructor,
    ) -> ExtractMicroFrontendsUseCase:

        return ExtractMicroFrontendsUseCase(
            repository_path=repository_path,
            reconstructor=reconstructor,
        )

    def extract_fragment_imports(
        self,
        repository_path: Path,
        reconstructor: Reconstructor,
    ) -> ExtractFragmentImportsUseCase:

        return ExtractFragmentImportsUseCase(
            repository_path=repository_path,
            reconstructor=reconstructor,
        )

    def extract_navigations(
        self,
        repository_path: Path,
        reconstructor: Reconstructor,
    ) -> ExtractNavigationsUseCase:

        return ExtractNavigationsUseCase(
            repository_path=repository_path,
            reconstructor=reconstructor,
        )

    def extract_api_calls(
        self,
        repository_path: Path,
        reconstructor: Reconstructor,
    ) -> ExtractApiCallsUseCase:

        return ExtractApiCallsUseCase(
            repository_path=repository_path,
            reconstructor=reconstructor,
        )

    def extract_state_accesses(
        self,
        repository_path: Path,
        reconstructor: Reconstructor,
    ) -> ExtractStateAccessesUseCase:

        return ExtractStateAccessesUseCase(
            repository_path=repository_path,
            reconstructor=reconstructor,
        )

    def extract_communications(
        self,
        repository_path: Path,
        spec_path: Path,
        reconstructor: Reconstructor,
    ) -> ExtractCommunicationsUseCase:

        return ExtractCommunicationsUseCase(
            repository_path=repository_path,
            spec_path=spec_path,
            reconstructor=reconstructor,
            specs=self.specs,
        )

    def resolve_domains(
        self,
        spec_path: Path,
    ) -> ResolveDomainsUseCase:

        return ResolveDomainsUseCase(
            spec_path=spec_path,
            specs=self.specs,
        )

    def setup_llm(
        self,
        endpoint: str | None = None,
        model: str | None = None,
        key: str | None = None,
    ) -> SetupLlmUseCase:

        return SetupLlmUseCase(
            settings=self.settings,
            endpoint=endpoint,
            model=model,
            key=key,
        )

    def setup_communication(
        self,
        destination: Path,
    ) -> SetupCommunicationUseCase:

        return SetupCommunicationUseCase(
            destination=destination,
            specs=self.specs,
        )

    def reconstruct(
        self,
        repository_path: Path,
        destination: Path | None,
        reconstructor: Reconstructor,
    ) -> ReconstructUseCase:

        return ReconstructUseCase(
            repository_path=repository_path,
            destination=destination,
            extract_microfrontends=self.extract_microfrontends(
                repository_path,
                reconstructor,
            ),
            extract_fragment_imports=self.extract_fragment_imports(
                repository_path,
                reconstructor,
            ),
            extract_navigations=self.extract_navigations(
                repository_path,
                reconstructor,
            ),
            extract_communications=self.extract_communications(
                repository_path,
                repository_path,
                reconstructor,
            ),
            extract_api_calls=self.extract_api_calls(
                repository_path,
                reconstructor,
            ),
            extract_state_accesses=self.extract_state_accesses(
                repository_path,
                reconstructor,
            ),
            resolve_domains=self.resolve_domains(repository_path),
            repository=self.repository,
        )

    def detect(
        self,
        source: Path,
        destination: Path | None,
        rules: list[Rule],
    ) -> DetectUseCase:

        return DetectUseCase(
            source=source,
            destination=destination,
            rules=rules,
            repository=self.repository,
        )

    def visualize(
        self,
        source: Path,
        destination: Path | None,
        renderer_name: str,
        detections_path: Path | None = None,
    ) -> VisualizeUseCase:

        return VisualizeUseCase(
            source=source,
            destination=destination,
            renderer=visualization.get(renderer_name),
            repository=self.repository,
            detections_path=detections_path,
        )
