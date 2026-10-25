"""
Composition root.

Único lugar do sistema que conhece implementações concretas. É
aqui que os registros são populados e que os casos de uso recebem
suas dependências injetadas. Todo o resto fala só com as portas
de `mfad.application.ports`.
"""

from __future__ import annotations

from pathlib import Path

from mfad.adapters.driven import antipatterns, reconstruction, visualization
from mfad.adapters.driven.antipatterns.rules import (
    CyclicDependency,
    GlobalStateCommunication,
    HammeringApis,
    HubLikeDependency,
    MegaFrontend,
    NanoFrontend,
    OneForAll,
)
from mfad.adapters.driven.reconstruction.singlespa.reconstructor import (
    SingleSpaReconstructor,
)
from mfad.adapters.driven.reconstruction.modulefederation import (
    ModuleFederationReconstructor,
)
from mfad.adapters.driven.provenance import GitSourceProbe
from mfad.adapters.driven.visualization.features import FeaturesRenderer
from mfad.adapters.driven.visualization.html import HtmlRenderer
from mfad.adapters.driven.storage import (
    JsonArtifactRepository,
    YamlSpecRepository,
)
from mfad.application.errors import UnsupportedPlatform
from mfad.application.ports import (
    ArtifactRepository,
    Reconstructor,
    Rule,
    SourceProbe,
    SpecRepository,
)
from mfad.application.use_cases import (
    ExtractApiCallsUseCase,
    DetectUseCase,
    ExtractMicroFrontendsUseCase,
    ExtractCommunicationsUseCase,
    ExtractCompositionsUseCase,
    ExtractNavigationsUseCase,
    ExtractStateAccessesUseCase,
    ReconstructUseCase,
    SetupCommunicationUseCase,
    VisualizeUseCase,
)


def bootstrap() -> None:
    """Popula os registros com o que vem de fábrica."""

    if reconstruction.available():
        return

    reconstruction.register(SingleSpaReconstructor())
    reconstruction.register(ModuleFederationReconstructor())

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

        self.probe: SourceProbe = GitSourceProbe()

    # ------------------------------------------------------------------
    # Resolução de implementações
    # ------------------------------------------------------------------

    def reconstructor(
        self,
        framework: str | None,
        repository_path: Path,
        organization_prefix: str | None = None,
    ) -> Reconstructor | None:

        # Plataforma com integração própria sai da varredura em qualquer
        # caso; se ela é o repositório inteiro, não sobra o que ler.
        platform = reconstruction.unsupported(repository_path)

        if platform:
            raise UnsupportedPlatform(repository_path, platform)

        if framework:
            chosen = reconstruction.get(framework)

        else:
            chosen = reconstruction.detect(repository_path)

            if not chosen:

                # Nada reconhecido no que sobrou depois de tirar os
                # pacotes de plataforma: o sistema é a plataforma.
                excluded = reconstruction.excluded(repository_path)

                if excluded:
                    platforms = sorted(excluded.values())
                    raise UnsupportedPlatform(
                        repository_path,
                        max(set(platforms), key=platforms.count),
                    )

                return None

        # O prefixo é opcional e específico de quem o suporta.
        if organization_prefix and hasattr(chosen, "organization_prefix"):
            chosen.organization_prefix = organization_prefix

        return chosen

    def excluded_packages(self, repository_path: Path) -> dict[str, str]:
        """Pacotes fora da análise por serem de plataforma não suportada."""

        return reconstruction.excluded(repository_path)

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

    def extract_compositions(
        self,
        repository_path: Path,
        reconstructor: Reconstructor,
    ) -> ExtractCompositionsUseCase:

        return ExtractCompositionsUseCase(
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
            extract_compositions=self.extract_compositions(
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
            repository=self.repository,
            probe=self.probe,
            reconstructor_name=reconstructor.name,
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
