"""O reconstrutor de arquiteturas single-spa."""

from __future__ import annotations

import json
from pathlib import Path

from damfe.application.ports import Reconstructor
from damfe.domain import (
    ApiCall,
    MicroFrontend,
    Communication,
    CommunicationSpec,
    FragmentImport,
    Navigation,
    StateAccess,
)
from damfe.adapters.driven.reconstruction.ast import AstReader, SourceTree
from damfe.adapters.driven.reconstruction.singlespa.microfrontends import MicroFrontendBuilder
from damfe.adapters.driven.reconstruction.singlespa.context import ScanContext
from damfe.adapters.driven.reconstruction.singlespa.fragment_imports import (
    FragmentImportExtractor,
)
from damfe.adapters.driven.reconstruction.singlespa.api_calls import (
    ApiCallExtractor,
)
from damfe.adapters.driven.reconstruction.singlespa.communications import (
    CommunicationExtractor,
)
from damfe.adapters.driven.reconstruction.singlespa.global_state import (
    GlobalStateExtractor,
)
from damfe.adapters.driven.reconstruction.singlespa.navigations import (
    NavigationExtractor,
)


class SingleSpaReconstructor(Reconstructor):

    name = "single-spa"

    description = (
        "Aplicações registradas via registerApplication, "
        "fragmentos exportados pelo entrypoint e telas "
        "declaradas pelo rootComponent."
    )

    def __init__(self, organization_prefix: str | None = None):
        self.organization_prefix = organization_prefix

        self._contexts: dict[Path, ScanContext] = {}

    # ------------------------------------------------------------------
    # Porta
    # ------------------------------------------------------------------

    def detect(self, repository: Path) -> bool:
        """
        Reconhece o repositório por dois sinais independentes:
        a dependência declarada e a chamada em si.
        """

        tree = SourceTree(repository)

        for manifest_file in tree.manifests():

            try:
                manifest = json.loads(
                    manifest_file.read_text(encoding="utf-8")
                )
            except Exception:
                continue

            dependencies = {
                **manifest.get("dependencies", {}),
                **manifest.get("devDependencies", {}),
            }

            if any(
                name == "single-spa" or name.startswith("single-spa-")
                for name in dependencies
            ):
                return True

        for file_path in tree.source_files():

            try:
                if "registerApplication" in file_path.read_text(
                    encoding="utf-8",
                    errors="ignore",
                ):
                    return True
            except OSError:
                continue

        return False

    def microfrontends(self, repository: Path) -> list[MicroFrontend]:

        context = self._context(repository)

        builder = MicroFrontendBuilder(context)

        found = sorted(
            (
                builder.build(registration)
                for registration in context.registrations
                if self._in_scope(registration.name)
            ),
            key=lambda item: item.id,
        )

        self._mark_shell(context, found)

        return found

    def fragment_imports(
        self,
        repository: Path,
        microfrontends: list[MicroFrontend],
    ) -> list[FragmentImport]:

        return FragmentImportExtractor(
            self._context(repository),
            microfrontends,
        ).extract()

    def navigations(
        self,
        repository: Path,
        microfrontends: list[MicroFrontend],
    ) -> list[Navigation]:

        return NavigationExtractor(
            self._context(repository),
            microfrontends,
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

        return ApiCallExtractor(
            self._context(repository),
            microfrontends,
        ).extract()

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
        """
        A varredura do repositório é cara e os dois passos da
        porta precisam dela. O contexto é memorizado por caminho
        para que chamá-los em sequência não pague duas vezes.
        """

        resolved = repository.resolve()

        if resolved not in self._contexts:
            self._contexts[resolved] = ScanContext.build(resolved)

        return self._contexts[resolved]


    # ------------------------------------------------------------------


    def _in_scope(self, name: str) -> bool:

        if not self.organization_prefix:
            return True

        return name.startswith(self.organization_prefix)

    def _mark_shell(
        self,
        context: ScanContext,
        microfrontends: list[MicroFrontend],
    ) -> None:
        """
        Marca como shell a aplicação que mora no mesmo pacote
        que declarou os registros. É ela que orquestra as demais.
        """

        directories = {
            context.relative(
                context.package_dir(registration.declared_in)
            )
            for registration in context.registrations
        }

        for microfrontend in microfrontends:

            if microfrontend.directory in directories:
                microfrontend.role = "shell"
