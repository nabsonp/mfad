"""
Module Federation reconstructor.

Only discovery changes. Navigation, external calls, global state and
communication are already generic — they start from the extracted
applications and from platform primitives, not from anything specific
to single-spa — and so they are reused as they are.

This boundary is the test of the architecture: if writing support for
a new technology required rewriting the five extractors, the split
between what belongs to the technology and what belongs to the domain
would be in the wrong place.
"""

from __future__ import annotations

from pathlib import Path

from mfad.application.ports import Reconstructor
from mfad.domain import (
    ApiCall,
    Communication,
    CommunicationSpec,
    Composition,
    MicroFrontend,
    Navigation,
    StateAccess,
)
from mfad.adapters.driven.reconstruction.ast import SourceTree
from mfad.adapters.driven.reconstruction.singlespa.context import ScanContext
from mfad.adapters.driven.reconstruction.singlespa.navigations import (
    NavigationExtractor,
)
from mfad.adapters.driven.reconstruction.singlespa.global_state import (
    GlobalStateExtractor,
)
from mfad.adapters.driven.reconstruction.singlespa import api_calls
from mfad.adapters.driven.reconstruction.singlespa.communications import (
    CommunicationExtractor,
)
from mfad.adapters.driven.reconstruction.modulefederation import config
from mfad.adapters.driven.reconstruction.modulefederation.microfrontends import (
    FederatedBuilder,
)
from mfad.adapters.driven.reconstruction.modulefederation.compositions import (
    RemoteImportExtractor,
)


class ModuleFederationReconstructor(Reconstructor):

    name = "module-federation"

    description = (
        "Federated units declared in webpack, Vite, Rspack or Nx."
    )

    def __init__(self, organization_prefix: str | None = None):
        self.organization_prefix = organization_prefix

        self._contexts: dict[Path, ScanContext] = {}
        self._federations: dict[Path, list] = {}

    # ------------------------------------------------------------------
    # Port
    # ------------------------------------------------------------------

    def detect(self, repository: Path) -> bool:
        """
        Recognize by the declaration itself, not by the dependency.

        The dependency name changes with the bundler — the webpack
        plugin, `@originjs/vite-plugin-federation`, the Nx one — and a
        list of them goes stale. The call that builds the federation is
        the same in all four.
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
    # Scan
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
