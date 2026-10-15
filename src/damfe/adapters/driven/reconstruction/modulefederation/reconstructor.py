"""
Reconstrutor de Module Federation.

Só a descoberta muda. Navegação, chamada externa, estado global e
comunicação já são genéricas — elas partem das aplicações extraídas e
de primitivas da plataforma, não de nada que o single-spa tenha —, e
por isso são reaproveitadas como estão.

Essa fronteira é o teste da arquitetura: se escrever o suporte a uma
tecnologia nova exigisse reescrever os cinco extratores, a separação
entre o que é da tecnologia e o que é do domínio estaria no lugar
errado.
"""

from __future__ import annotations

from pathlib import Path

from damfe.application.ports import Reconstructor
from damfe.domain import (
    ApiCall,
    Communication,
    CommunicationSpec,
    Composition,
    MicroFrontend,
    Navigation,
    StateAccess,
)
from damfe.adapters.driven.reconstruction.ast import SourceTree
from damfe.adapters.driven.reconstruction.singlespa.context import ScanContext
from damfe.adapters.driven.reconstruction.singlespa.navigations import (
    NavigationExtractor,
)
from damfe.adapters.driven.reconstruction.singlespa.global_state import (
    GlobalStateExtractor,
)
from damfe.adapters.driven.reconstruction.singlespa import api_calls
from damfe.adapters.driven.reconstruction.singlespa.communications import (
    CommunicationExtractor,
)
from damfe.adapters.driven.reconstruction.modulefederation import config
from damfe.adapters.driven.reconstruction.modulefederation.microfrontends import (
    FederatedBuilder,
)
from damfe.adapters.driven.reconstruction.modulefederation.compositions import (
    RemoteImportExtractor,
)


class ModuleFederationReconstructor(Reconstructor):

    name = "module-federation"

    description = (
        "Unidades federadas declaradas em webpack, Vite, Rspack ou Nx."
    )

    def __init__(self, organization_prefix: str | None = None):
        self.organization_prefix = organization_prefix

        self._contexts: dict[Path, ScanContext] = {}
        self._federations: dict[Path, list] = {}

    # ------------------------------------------------------------------
    # Porta
    # ------------------------------------------------------------------

    def detect(self, repository: Path) -> bool:
        """
        Reconhece pela declaração em si, não pela dependência.

        A dependência muda de nome conforme o empacotador — o plugin
        do webpack, `@originjs/vite-plugin-federation`, o do Nx — e
        uma lista delas envelhece. A chamada que constrói a federação
        é a mesma nos quatro.
        """

        tree = SourceTree(repository)

        for file_path in tree.source_files():

            if not config.is_config(file_path):
                continue

            try:
                content = file_path.read_text(
                    encoding="utf-8", errors="ignore"
                )
            except OSError:
                continue

            if any(name in content for name in config.DECLARATIONS):
                return True

        return False

    def microfrontends(self, repository: Path) -> list[MicroFrontend]:

        context = self._context(repository)

        found = FederatedBuilder(
            context,
            self._declarations(repository),
        ).build()

        return [item for item in found if self._in_scope(item.id)]

    def compositions(
        self,
        repository: Path,
        microfrontends: list[MicroFrontend],
    ) -> list[Composition]:

        return RemoteImportExtractor(
            self._context(repository),
            microfrontends,
        ).extract()

    def navigations(
        self,
        repository: Path,
        microfrontends: list[MicroFrontend],
    ) -> list[Navigation]:

        context = self._context(repository)

        return NavigationExtractor(
            context,
            microfrontends,
            requests=api_calls.extracted(context, microfrontends)[1],
        ).extract()

    def state_accesses(
        self,
        repository: Path,
        microfrontends: list[MicroFrontend],
    ) -> list[StateAccess]:

        return GlobalStateExtractor(
            self._context(repository),
            microfrontends,
        ).extract()

    def api_calls(
        self,
        repository: Path,
        microfrontends: list[MicroFrontend],
    ) -> list[ApiCall]:

        return api_calls.extracted(self._context(repository), microfrontends)[0]

    def communications(
        self,
        repository: Path,
        microfrontends: list[MicroFrontend],
        spec: CommunicationSpec,
    ) -> list[Communication]:

        return CommunicationExtractor(
            self._context(repository),
            microfrontends,
            spec,
        ).extract()

    # ------------------------------------------------------------------
    # Varredura
    # ------------------------------------------------------------------

    def _context(self, repository: Path) -> ScanContext:

        resolved = repository.resolve()

        if resolved not in self._contexts:
            self._contexts[resolved] = ScanContext.build(resolved)

        return self._contexts[resolved]

    def _declarations(self, repository: Path) -> list:

        resolved = repository.resolve()

        if resolved in self._federations:
            return self._federations[resolved]

        context = self._context(repository)

        found = []

        for file_path in context.tree.source_files():

            if not config.is_config(file_path):
                continue

            try:
                root, source = context.reader.parse(file_path)
            except Exception:
                continue

            found.extend(config.read(file_path, root, source))

        self._federations[resolved] = found

        return found

    def _in_scope(self, name: str) -> bool:

        if not self.organization_prefix:
            return True

        return name.startswith(self.organization_prefix)
