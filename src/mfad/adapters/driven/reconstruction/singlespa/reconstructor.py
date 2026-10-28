"""The reconstructor of single-spa architectures."""

from __future__ import annotations

import json
from pathlib import Path

from mfad.application.ports import Reconstructor
from mfad.domain import (
    ApiCall,
    MicroFrontend,
    Communication,
    CommunicationSpec,
    Composition,
    Navigation,
    StateAccess,
)
from mfad.adapters.driven.reconstruction.ast import SourceTree
from mfad.adapters.driven.reconstruction.singlespa.microfrontends import MicroFrontendBuilder
from mfad.adapters.driven.reconstruction.singlespa.context import (
    ScanContext,
    unscoped,
)
from mfad.adapters.driven.reconstruction.singlespa import discovery
from mfad.adapters.driven.reconstruction.singlespa.compositions import (
    CompositionExtractor,
)
from mfad.adapters.driven.reconstruction.singlespa import api_calls
from mfad.adapters.driven.reconstruction.singlespa.communications import (
    CommunicationExtractor,
)
from mfad.adapters.driven.reconstruction.singlespa.global_state import (
    GlobalStateExtractor,
)
from mfad.adapters.driven.reconstruction.singlespa.navigations import (
    NavigationExtractor,
)


class SingleSpaReconstructor(Reconstructor):

    name = "single-spa"

    description = (
        "Applications registered via registerApplication, "
        "fragments exported by the entrypoint and screens "
        "declared by the rootComponent."
    )

    def __init__(self, organization_prefix: str | None = None):
        self.organization_prefix = organization_prefix

        self._contexts: dict[Path, ScanContext] = {}

    # ------------------------------------------------------------------
    # Port
    # ------------------------------------------------------------------

    def detect(self, repository: Path) -> bool:
        """
        Recognizes the repository by two independent signals: the
        declared dependency and the call itself.
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

        registrations = [
            registration
            for registration in context.registrations
            if self._in_scope(registration.name)
        ]

        # Bottom-up discovery, for what the registration does not
        # name. See `discovery.by_lifecycles`.
        registrations += discovery.by_lifecycles(
            context,
            builder._exports,
            {
                path.resolve()
                for registration in registrations
                for path in [self._package_of(context, registration)]
                if path
            },
            self._in_scope,
        )

        found = sorted(
            (builder.build(registration) for registration in registrations),
            key=lambda item: item.id,
        )

        self._mark_shell(context, found)

        return found

    @staticmethod
    def _package_of(context, registration) -> Path | None:
        """The package directory a registered application occupies."""

        if registration.specifier and not registration.specifier.startswith("."):
            return context.packages.get(registration.specifier)

        return context.package_dir(registration.declared_in)

    def compositions(
        self,
        repository: Path,
        microfrontends: list[MicroFrontend],
    ) -> list[Composition]:

        return CompositionExtractor(
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
        """
        Scanning the repository is expensive and both steps of the port
        need it. The context is memoized by path so that calling them
        in sequence does not pay twice.
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
        Adds the orchestrator to the graph, as a node with the `shell` role.

        It does not appear in `registerApplication` — it is the caller —
        and so it was left out, even though it is what mounts all the
        others. The graph without it shows loose micro frontends, with
        nothing explaining how they reach the page: it is the most
        important relationship in the system, and it was the only one
        missing.

        Marking as shell the application that LIVES in the same package
        as the orchestrator, as was done before, is something else and
        was wrong: a monolith loaded by relative path from the
        root-config is a registered application like the others, not
        the orchestrator.
        """

        # One shell per orchestrator. A repository may contain more than
        # one system — the example one here contains two —, and merging
        # the registrations of all of them into a single node would
        # invent an orchestrator that mounts applications of different systems.
        #: package → (declaring file, mounted names)
        by_package: dict[Path, tuple[Path, set[str]]] = {}

        for registration in context.registrations:

            directory = context.package_dir(registration.declared_in)

            by_package.setdefault(
                directory, (registration.declared_in, set())
            )[1].add(registration.name)

        # Under single-spa-layout the registration is `applications.forEach(
        # registerApplication)`, with no literal name at all. The mounter
        # is the package that declares the layout, and what it mounts are
        # the applications the layout names.
        for layout_file, declared in sorted(context.layouts.items()):

            directory = context.package_dir(layout_file)

            by_package.setdefault(directory, (layout_file, set()))[1].update(
                declared
            )

        known = {item.id for item in microfrontends}

        shells = []

        for directory, (declared_in, names) in sorted(by_package.items()):

            relative = context.relative(directory)

            identifier = self._shell_id(directory, relative)

            if identifier in known:
                continue

            shell = MicroFrontend(
                id=identifier,
                role="shell",
                directory=relative,
                entrypoint=context.relative(declared_in),
            )

            shell.size = context.size_of(directory)

            # What it mounts. It is the system's composition edge: the
            # shell picks the application by URL and puts it on the page.
            shell.mounts = sorted(
                {self._mounted(name, microfrontends) for name in names}
            )

            shells.append(shell)

        microfrontends[:0] = shells

    @staticmethod
    def _mounted(name: str, microfrontends: list[MicroFrontend]) -> str:
        """
        The identifier of the mounted unit, when it is in the inventory.

        The orchestrator names it by the import map specifier; the unit
        found through the lifecycles is named by its `package.json`.
        Same rule as `ScanContext.layout_routes_of`: equal, or equal
        without the scope. Otherwise the name stays as it is — the unit
        may not be in the repository.
        """

        ids = {item.id for item in microfrontends}

        if name in ids:
            return name

        wanted = unscoped(name)

        matches = [item for item in ids if unscoped(item) == wanted]

        return matches[0] if len(matches) == 1 else name

    @staticmethod
    def _shell_id(directory: Path, relative: str) -> str:
        """The name declared in `package.json`, or the directory."""

        manifest_file = directory / "package.json"

        try:
            manifest = json.loads(
                manifest_file.read_text(encoding="utf-8")
            )
        except Exception:
            return relative or "shell"

        return manifest.get("name") or relative or "shell"
