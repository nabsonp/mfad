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
        Acrescenta o orquestrador ao grafo, como nó de papel `shell`.

        Ele não aparece em `registerApplication` — é quem chama — e
        por isso ficava de fora, embora seja quem monta todos os
        outros. O grafo sem ele mostra micro frontends soltos, sem
        nada explicando como chegam à página: é a relação mais
        importante do sistema, e era a única ausente.

        Marcar como shell a aplicação que MORA no mesmo pacote do
        orquestrador, como se fazia antes, é outra coisa e estava
        errado: um monolito carregado por caminho relativo a partir
        do root-config é aplicação registrada como as demais, não o
        orquestrador.
        """

        # Um shell por orquestrador. Um repositório pode conter mais
        # de um sistema — o de exemplo aqui contém dois —, e juntar
        # os registros de todos num nó só inventaria um orquestrador
        # que monta aplicações de sistemas diferentes.
        by_package: dict[Path, list] = {}

        for registration in context.registrations:

            directory = context.package_dir(registration.declared_in)

            by_package.setdefault(directory, []).append(registration)

        known = {item.id for item in microfrontends}

        shells = []

        for directory, registrations in sorted(by_package.items()):

            relative = context.relative(directory)

            identifier = self._shell_id(directory, relative)

            if identifier in known:
                continue

            shell = MicroFrontend(
                id=identifier,
                role="shell",
                directory=relative,
                entrypoint=context.relative(registrations[0].declared_in),
            )

            shell.size = context.size_of(directory)

            # Quem ele monta. É a aresta de composição do sistema: o
            # shell escolhe a aplicação por URL e a põe na página.
            shell.mounts = sorted(
                registration.name for registration in registrations
            )

            shells.append(shell)

        microfrontends[:0] = shells

    @staticmethod
    def _shell_id(directory: Path, relative: str) -> str:
        """O nome declarado no `package.json`, ou o diretório."""

        manifest_file = directory / "package.json"

        try:
            manifest = json.loads(
                manifest_file.read_text(encoding="utf-8")
            )
        except Exception:
            return relative or "shell"

        return manifest.get("name") or relative or "shell"
