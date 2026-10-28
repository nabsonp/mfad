"""
The federated units and what each one contains.

The difference from single-spa lies here, and only here. There, an
orchestrator declares everyone; here each unit declares itself, and
the system is what emerges when the declarations are read together.

Three consequences that change the extraction:

There is no `activeWhen`. Module Federation handles loading remote
code and says nothing about URLs. A unit's routes are those of its own
router, and they only exist if it has one.

There is no declared shell role. Host and hosted are not mutually
exclusive: a unit can consume remotes and be consumed at the same
time. What can be stated is who consumes without being consumed, and
that is what gets marked.

A fragment is an `exposes` entry, which is an explicit declaration — a
better signal than any named export, which is all single-spa leaves.
"""

from __future__ import annotations

from pathlib import Path

from mfad.domain import Fragment, MicroFrontend, Screen
from mfad.adapters.driven.reconstruction.singlespa.declarations import relocate
from mfad.adapters.driven.reconstruction.ast import AstReader, ImportTable, ModuleResolver
from mfad.adapters.driven.reconstruction.routers import (
    AngularRouteReader,
    ReactRouteReader,
)
from mfad.adapters.driven.reconstruction.singlespa.context import ScanContext
from mfad.adapters.driven.reconstruction.modulefederation import (
    config,
    specifiers,
)


class FederatedBuilder:

    def __init__(self, context: ScanContext, federations: list):
        self.context = context
        self.federations = federations

        #: unit -> published paths, without the "./"
        self.catalog = {
            federation.name: {
                path.lstrip("./") for path in federation.exposes
            }
            for federation in federations
        }

        self.by_name = {
            federation.name: federation for federation in federations
        }

    def build(self) -> list[MicroFrontend]:

        consumed = {
            remote
            for federation in self.federations
            for remote in federation.remotes
        }

        found = []

        for federation in self.federations:

            found.append(self._one(federation, consumed))

        self._reattribute(found)

        return found

    def _reattribute(self, microfrontends: list[MicroFrontend]) -> None:
        """
        Give back to the provider the screen the shell only routes to.

        `<Route path="/pharmacy" element={<Pharmacy/>}/>` with
        `Pharmacy` coming from `import("hs-pharmacy/Pharmacy")` declares
        a shell route to a screen that belongs to the remote. The route
        lives in the host's router; the screen belongs to the publisher.

        Leaving both with the host produced a shell owning every
        business route and remotes with no route at all — the opposite
        of what the system does. `_screens` already marks the provider
        in `screen.microfrontend`; here the screens are moved.
        """

        index = {item.id: item for item in microfrontends}

        for item in microfrontends:

            keep = []

            for screen in item.screens:

                target = index.get(screen.microfrontend)

                if target is None or target is item:
                    keep.append(screen)
                    continue

                target.screens.append(screen)

            item.screens = keep

        for item in microfrontends:

            item.routes = sorted(
                {screen.route for screen in item.screens if screen.route}
            )

    def _one(self, federation, consumed: set[str]) -> MicroFrontend:

        directory = self.context.package_dir(federation.declared_in)

        microfrontend = MicroFrontend(
            id=federation.name,
            directory=self.context.relative(directory),
            entrypoint=self.context.relative(federation.declared_in),
            size=self.context.size_of(directory),
        )

        published = config.package_name(directory)

        if published and published != federation.name:
            microfrontend.metadata["package"] = published

        barrels = 0

        for path, target in sorted(federation.exposes.items()):

            resolved = self._resolve(directory, target)

            microfrontend.fragments.append(
                Fragment(
                    name=path,
                    microfrontend=federation.name,
                    file=resolved,
                )
            )

            barrels += self._reexports(resolved)

        # Library shape: the exposed module only re-exports instead of
        # defining what it publishes. The unit delivers a catalog of
        # pieces, not a piece.
        #
        # This is a signal, not a classification. A library exposing
        # component by component has no barrel, and a remote can expose
        # a barrel of pages — the shape gets the common case right but
        # does not prove what the thing is. Whoever reads decides
        # whether it is a library, which is why the number is recorded
        # instead of changing how the rules behave.
        if barrels:
            microfrontend.metadata["reexports"] = barrels

        if federation.remotes:
            microfrontend.metadata["remotes"] = sorted(federation.remotes)

        if federation.shared:
            microfrontend.metadata["shared"] = federation.shared

        # Consumes remotes and is consumed by no one: it is the tip of
        # the composition, the closest thing to a shell that Module
        # Federation defines. When everyone consumes each other, no one
        # is.
        if federation.remotes and federation.name not in consumed:
            microfrontend.role = "shell"
            microfrontend.mounts = sorted(federation.remotes)

        microfrontend.screens = self._screens(directory, federation.name)

        microfrontend.routes = sorted(
            {screen.route for screen in microfrontend.screens if screen.route}
        )

        relocate(self.context, microfrontend)

        return microfrontend

    def _remote_names(self, root, source) -> dict[str, tuple[str, str]]:
        """
        Local name -> (publishing unit, published path).

        Covers both ways of crossing the boundary: the static import
        and the dynamic `import()`, which is how a host loads a remote
        page.
        """

        records = [
            (record.module, record.local_name)
            for record in ImportTable.records(root, source)
        ] + [
            (module, local_name)
            for module, local_name, _, _ in specifiers.dynamic_imports(
                root, source
            )
        ]

        found = {}

        for module, local_name in records:

            provider, exposed = specifiers.split(module, self.catalog)

            if provider:
                found[local_name] = (provider, exposed)

        return found

    def _exposed_file(self, provider: str, exposed: str) -> str | None:
        """The internal file the provider publishes under that path."""

        federation = self.by_name.get(provider)

        if not federation:
            return None

        target = (
            federation.exposes.get(f"./{exposed}")
            or federation.exposes.get(exposed)
        )

        if not target:
            return None

        return self._resolve(
            self.context.package_dir(federation.declared_in), target
        )

    def _resolve(self, directory: Path, target: str) -> str | None:
        """The internal file an `exposes` entry points to."""

        if not target:
            return None

        base = (directory / target).resolve()

        # Appending the extension comes before replacing the suffix:
        # `./x.component` is `x.component.ts`, not `x.ts`.
        for candidate in [base] + [
            base.parent / f"{base.name}{extension}"
            for extension in (".js", ".jsx", ".ts", ".tsx")
        ] + [
            base.with_suffix(extension)
            for extension in (".js", ".jsx", ".ts", ".tsx")
        ] + [
            base / f"index{extension}"
            for extension in (".js", ".jsx", ".ts", ".tsx")
        ]:
            if candidate.is_file():
                return self.context.relative(candidate)

        return None

    def _reexports(self, relative: str | None) -> int:
        """
        How many names the module re-exports without defining them.

        `export { Card } from "./ui/card"` counts; `export default
        function Pharmacy()` does not. Zero means the module defines
        what it publishes.
        """

        if not relative:
            return 0

        path = self.context.repository / relative

        if not path.is_file():
            return 0

        try:
            root, source = self.context.reader.parse(path)
        except Exception:
            return 0

        found = 0

        for node in AstReader.find_all(root, "export_statement"):

            text = AstReader.text(node, source)

            if " from " not in text:
                continue

            for clause in node.named_children:

                if clause.type != "export_clause":
                    continue

                found += sum(
                    1
                    for child in clause.named_children
                    if child.type == "export_specifier"
                )

        return found

    def _screens(self, directory: Path, owner: str) -> list[Screen]:
        """
        The screens declared by the unit's own router.

        Without `activeWhen` there is no route coming from the
        registry, so a screen here only exists when the unit has a
        router. A unit that only publishes components has no screens
        at all, and that is the correct result — it answers for no
        URL.
        """

        found: list[Screen] = []

        seen: set[tuple[str, str]] = set()

        directory = directory.resolve()

        for file_path in sorted(
            path
            for path in self.context.tree.source_files()
            if directory in path.resolve().parents
        ):
            try:
                root, source = self.context.reader.parse(file_path)
            except Exception:
                continue

            imports = ImportTable(root, source, file_path)

            for screen in AngularRouteReader(self.context).screens_in(
                file_path, owner
            ):
                key = (screen.component, screen.route or "")

                if key in seen:
                    continue

                seen.add(key)
                found.append(screen)

            # Local name -> unit that publishes it, for both ways of
            # crossing the boundary: `import X from "remote/X"` and
            # `const X = lazy(() => import("remote/X"))`.
            remote_of = self._remote_names(root, source)

            for entry in ReactRouteReader(self.context.routes).routes_in(
                root, source
            ):
                key = (entry.component, entry.route or "")

                if key in seen:
                    continue

                seen.add(key)

                # `lazy: () => import("remote/Pagina")` points straight
                # at the module; in the other forms it is the local name.
                provider, exposed = (
                    specifiers.split(entry.specifier, self.catalog)
                    if entry.specifier
                    else remote_of.get(entry.component, (None, ""))
                )

                if provider:
                    # The screen belongs to whoever publishes the module,
                    # even if the route is declared in the host's router.
                    file = self._exposed_file(provider, exposed)

                else:
                    # The screen's file is the COMPONENT's, not the
                    # router's. Pointing at the router makes every screen
                    # reach everything it imports, and assigning
                    # fragments to screens turns into noise: each screen
                    # gets the dependencies of all the others.
                    target = (
                        ModuleResolver.resolve(entry.specifier, file_path)
                        if entry.specifier
                        else imports.file_for(entry.component)
                    )

                    file = (
                        self.context.relative(target)
                        if target
                        else self.context.relative(file_path)
                    )

                found.append(
                    Screen(
                        component=entry.component,
                        microfrontend=provider or owner,
                        route=entry.route,
                        route_expression=entry.expression,
                        file=file,
                        line=entry.line,
                    )
                )

        return found
