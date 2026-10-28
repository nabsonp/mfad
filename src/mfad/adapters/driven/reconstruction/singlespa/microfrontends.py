"""
Building the applications from the `registerApplication` calls.

Fragments are the entrypoint's exports that are not part of the
single-spa lifecycle contract. Screens are the `<Route>` elements
declared by the `rootComponent`.
"""

from __future__ import annotations

import json
import re

from pathlib import Path

from tree_sitter import Node

from mfad.domain import Fragment, MicroFrontend, Screen
from mfad.adapters.driven.reconstruction.routers import (
    ReactRouteReader,
    AngularRouteReader,
)
from mfad.adapters.driven.reconstruction.ast import AstReader, ImportTable, ModuleResolver
from mfad.adapters.driven.reconstruction.singlespa.context import Registration, ScanContext
from mfad.adapters.driven.reconstruction.singlespa import jsx
from mfad.adapters.driven.reconstruction.singlespa.declarations import relocate
from mfad.adapters.driven.reconstruction.singlespa.exported_values import ExportedValues
from mfad.adapters.driven.reconstruction.singlespa.reachability import (
    Reachability,
)


LIFECYCLE_NAMES = {"bootstrap", "mount", "unmount", "update"}


class MicroFrontendBuilder:

    def __init__(self, context: ScanContext):
        self.context = context

    def build(self, registration: Registration) -> MicroFrontend:

        entrypoint = self._entrypoint_for(registration)

        microfrontend = MicroFrontend(
            id=registration.name,
            routes=registration.active_when,
            directory=(
                self.context.relative(
                    self.context.package_dir(entrypoint)
                )
                if entrypoint
                else ""
            ),
            entrypoint=(
                self.context.relative(entrypoint) if entrypoint else ""
            ),
        )

        # A registered application whose entrypoint does not resolve is
        # still a node of the graph. Vanishing is worse than appearing incomplete.
        if not entrypoint:
            microfrontend.metadata["entrypoint_resolved"] = False
            return microfrontend

        microfrontend.size = self.context.size_of(
            self.context.package_dir(entrypoint)
        )

        root, source = self.context.reader.parse(entrypoint)

        imports = ImportTable(root, source, entrypoint)

        lifecycles, exported = self._exports(root, source)

        microfrontend.metadata["lifecycles"] = sorted(lifecycles)

        values = ExportedValues(self.context.reader)

        for name, line in exported:

            # Text, list, type: leaves through `export`, but nobody mounts it.
            if values.is_data(entrypoint, name):
                continue

            # `export { Card } from "./Card"` does not matter: follow the re-export.
            target = imports.file_for(name) or values.origin(entrypoint, name)

            microfrontend.fragments.append(
                Fragment(
                    name=name,
                    microfrontend=microfrontend.id,
                    file=(
                        self.context.relative(target) if target else None
                    ),
                    line=line,
                )
            )

        # Under single-spa-layout the routes are not in the registration:
        # they live in the template, and the registration has no activeWhen at all.
        if not microfrontend.routes:

            declared = self.context.layout_routes_of(registration.name)

            if declared:
                microfrontend.routes = declared
                microfrontend.metadata["routes_from"] = "single-spa-layout"

        # Third source, Angular's own: single-spa-angular requires
        # declaring `APP_BASE_HREF` with the prefix where the application
        # is mounted, so that the internal router works under it. It is
        # the `activeWhen` written on the application's side — and it
        # exists even when the orchestrator is not in the repository.
        if not microfrontend.routes:

            base = self._base_href(self.context.package_dir(entrypoint))

            if base:
                microfrontend.routes = [base]
                microfrontend.metadata["routes_from"] = "APP_BASE_HREF"

        # The form of activeWhen travels along: a route coming from an
        # activity function does not have the same confidence as a
        # literal route, and whoever reads the artifact needs to tell them apart.
        if registration.active_when_form != "literal":
            microfrontend.metadata["active_when_form"] = (
                registration.active_when_form
            )

        if registration.custom_props:
            microfrontend.metadata["custom_props"] = (
                registration.custom_props
            )

        container = self._container_of(root, source)

        if container:
            microfrontend.metadata["container"] = container

        root_component = self._root_component_file(root, source, imports)

        microfrontend.screens = self._screens(microfrontend, root_component)

        if not microfrontend.screens and root_component:
            self._root_without_router(root_component, microfrontend)

        relocate(self.context, microfrontend)

        return microfrontend

    def _entrypoint_for(
        self,
        registration: Registration,
    ) -> Path | None:
        """
        The entry file of the registered micro frontend.

        Two ways, in this order. The package index resolves the import
        map specifier — `@org/mfe-x` — to the directory that declares
        that name in `package.json`, which is the reliable way. The
        naming convention is the fallback when the package is not in
        the analyzed repository.

        A registered application without its own package does exist:
        the shell may declare lifecycles inline. Returning `None` here
        is a legitimate answer, and `build` keeps it in the graph marked
        as unresolved.
        """

        if registration.entrypoint:
            return registration.entrypoint

        specifier = registration.specifier

        if not specifier:
            return None

        # Relative path: the shell loads the module from its own
        # repository, without a published package. That is how a
        # monolith being migrated enters the graph — it is a registered
        # application like any other, and vanishes if we only look at the import map.
        if specifier.startswith("."):
            return ModuleResolver.resolve(
                specifier, registration.declared_in
            )

        directory = self.context.packages.get(specifier)

        if directory:

            found = self._by_convention(directory, specifier)

            if found:
                return found

            # Package found, entry outside the convention: the manifest's
            # `main`/`module` field is the project's own declaration of
            # where it starts.
            return self._from_manifest(directory)

        for candidate in self.context.tree.manifests():

            found = self._by_convention(candidate.parent, specifier)

            if found:
                return found

        return None

    def _base_href(self, directory: Path) -> str | None:
        """
        The prefix of `{ provide: APP_BASE_HREF, useValue: "/x/" }`.

        Only a single literal value: more than one distinct prefix in
        the same package does not say which one is the mount's. `/` does
        not work either — it says the application is at the root, not
        that it owns it.
        """

        found: set[str] = set()

        for file_path in self.context.tree.source_files():

            if directory not in file_path.parents:
                continue

            try:
                root, source = self.context.reader.parse(file_path)
            except Exception:
                continue

            if b"APP_BASE_HREF" not in source:
                continue

            for node in AstReader.find_all(root, "object"):

                fields = {}

                for pair in node.named_children:

                    if pair.type != "pair":
                        continue

                    key = pair.child_by_field_name("key")
                    value = pair.child_by_field_name("value")

                    if key and value:
                        fields[AstReader.text(key, source)] = value

                provide = fields.get("provide")
                value = fields.get("useValue")

                if (
                    provide is None
                    or value is None
                    or AstReader.text(provide, source) != "APP_BASE_HREF"
                    or value.type != "string"
                ):
                    continue

                route = "/" + AstReader.strip_quotes(
                    AstReader.text(value, source)
                ).strip("/")

                if route != "/":
                    found.add(route)

        return found.pop() if len(found) == 1 else None

    @staticmethod
    def _by_convention(directory: Path, package_name: str) -> Path | None:
        """`@org/mfe-checkout` → `src/org-mfe-checkout.{js,jsx,ts,tsx}`."""

        organization, _, project = package_name.partition("/")

        organization = organization.lstrip("@")

        if not project:
            return None

        for extension in ModuleResolver.EXTENSIONS:

            candidate = (
                directory / "src" / f"{organization}-{project}{extension}"
            )

            if candidate.is_file():
                return candidate

        return None

    @staticmethod
    def _from_manifest(directory: Path) -> Path | None:
        """What `package.json` declares as the starting point."""

        manifest_file = directory / "package.json"

        try:
            manifest = json.loads(
                manifest_file.read_text(encoding="utf-8")
            )
        except Exception:
            return None

        for field_name in ("module", "main", "source"):

            declared = manifest.get(field_name)

            if not declared:
                continue

            candidate = (directory / declared).resolve()

            if candidate.is_file():
                return candidate

        return None

    def _exports(
        self,
        root: Node,
        source: bytes,
    ) -> tuple[list[str], list[tuple[str, int]]]:
        """
        What the entry file exposes.

        Returns two sets. The lifecycles — `bootstrap`, `mount`,
        `unmount`, `update` — say that it is a single-spa micro
        frontend. Everything else that leaves through `export` is a
        fragment: a component published for another micro frontend to
        consume.
        """

        lifecycles: list[str] = []
        exported: list[tuple[str, int]] = []

        for node in AstReader.find_all(root, "export_statement"):

            # export const { bootstrap, mount, unmount } = lifecycles;
            declaration = node.child_by_field_name("declaration")

            if declaration:

                # Only the variables the declaration itself creates.
                # Descending into the whole tree also picked up the locals
                # inside exported functions — the `let el` of
                # `export function domElementGetter() {...}` became a
                # fragment.
                declarators = [
                    child
                    for child in declaration.named_children
                    if child.type == "variable_declarator"
                ]

                patterns = [
                    pattern
                    for declarator in declarators
                    if (target := declarator.child_by_field_name("name")) is not None
                    for pattern in AstReader.find_all(
                        target, "shorthand_property_identifier_pattern"
                    )
                ]

                for pattern in patterns:
                    name = AstReader.text(pattern, source)

                    if name in LIFECYCLE_NAMES:
                        lifecycles.append(name)

                # export const bootstrap = lifecycles.bootstrap;
                #
                # The third form, and the one the Angular adapters
                # generate. Without it, a unit that exports the
                # lifecycles one by one is not recognized as a micro
                # frontend, and a component exported this way is not
                # recognized as a fragment.
                for declarator in declarators:
                    name_node = declarator.child_by_field_name("name")

                    if not name_node or name_node.type != "identifier":
                        continue

                    name = AstReader.text(name_node, source)

                    if name in LIFECYCLE_NAMES:
                        lifecycles.append(name)
                    else:
                        exported.append(
                            (name, name_node.start_point[0] + 1)
                        )

                continue

            # export { DeliveryEstimateFragment, ... };
            for clause in node.children:

                if clause.type != "export_clause":
                    continue

                for specifier in clause.named_children:

                    if specifier.type != "export_specifier":
                        continue

                    alias = specifier.child_by_field_name("alias")
                    name_node = specifier.child_by_field_name("name")

                    chosen = alias or name_node

                    if not chosen:
                        continue

                    name = AstReader.text(chosen, source)

                    if name in LIFECYCLE_NAMES:
                        lifecycles.append(name)
                        continue

                    exported.append((name, chosen.start_point[0] + 1))

        return lifecycles, exported

    def _container_of(self, root: Node, source: bytes) -> str | None:
        """
        The shell element in which this micro frontend is mounted.

        `domElementGetter` is how single-spa lets the application
        choose where to appear, and `domElement` is the direct form the
        framework adapters accept. Declaring it means the shell reserved
        a place in the layout — `#navbar-container` —, and that the thing
        is slotted into a page together with other things. An
        application that does not declare it gets a `div` that
        single-spa appends to the body, and takes up the page alone.

        It is the strongest signal there is to tell composition from
        screen, and it depends on no folder or naming convention.
        """

        for pair in AstReader.find_all(root, "pair"):

            key_node = pair.child_by_field_name("key")
            value_node = pair.child_by_field_name("value")

            if not key_node or not value_node:
                continue

            key = AstReader.strip_quotes(AstReader.text(key_node, source))

            if key not in ("domElementGetter", "domElement"):
                continue

            expression = AstReader.text(value_node, source)

            # getElementById("navbar-container") · querySelector("#x")
            found = re.search(
                r"""getElementById\(\s*["'](?P<id>[^"']+)["']"""
                r"""|querySelector\(\s*["']#?(?P<sel>[^"']+)["']""",
                expression,
            )

            if not found:
                return "declarado"

            return found.group("id") or found.group("sel")

        return None

    def _root_component_file(
        self,
        root: Node,
        source: bytes,
        imports: ImportTable,
    ) -> Path | None:

        # singleSpaReact({ rootComponent: App, ... })
        for pair in AstReader.find_all(root, "pair"):

            key_node = pair.child_by_field_name("key")
            value_node = pair.child_by_field_name("value")

            if not key_node or not value_node:
                continue

            key = AstReader.strip_quotes(AstReader.text(key_node, source))

            if key != "rootComponent":
                continue

            return imports.file_for(AstReader.text(value_node, source))

        return None

    def _root_without_router(
        self,
        root_component: Path,
        microfrontend: MicroFrontend,
    ) -> None:
        """
        What the root component is, when the micro frontend has no
        router of its own.

        In single-spa the router is `activeWhen`: a micro frontend
        registered under a prefix already serves that route, and an
        internal router is only needed to serve several screens under
        the same prefix. So the absence of `<Route>` does not mean the
        absence of a screen — it means a single screen.

        The signal that it is composition, and not a screen, is the
        declared container. `domElementGetter` pointing to a shell
        element means the layout reserved a place for it — it is
        slotted into a page together with other things. An application
        that does not declare it gets a `div` appended to the body.

        Without it, the root component is the screen of that prefix.
        The route is the registration's; there is no expression to
        resolve, because it was not written in the screen's code.
        """

        name = root_component.stem

        if self._is_fragment(microfrontend):

            if any(item.name == name for item in microfrontend.fragments):
                return

            microfrontend.fragments.append(
                Fragment(
                    name=name,
                    microfrontend=microfrontend.id,
                    file=self.context.relative(root_component),
                )
            )

            return

        # A root that only mounts providers around a project component
        # is not the screen: the screen is what it wraps.
        name, content = self._content_of(root_component)

        microfrontend.screens = [
            Screen(
                component=name,
                microfrontend=microfrontend.id,
                route=microfrontend.routes[0] if microfrontend.routes else None,
                file=self.context.relative(content),
            )
        ]

    def _content_of(self, root_component: Path) -> tuple[str, Path]:
        """
        The component the root shows, descending through the ones that only wrap.

        A component only wraps when what it renders are package
        components (`<Provider>`, `<LocationProvider>`, React's
        `<Suspense>`) and a single project component, with no HTML
        element of its own. The screen is the first one that is not
        like that.
        """

        name, current = root_component.stem, root_component

        for _ in range(4):

            try:
                root, source = self.context.reader.parse(current)
            except Exception:
                break

            imports = ImportTable(root, source, current)

            own: list[tuple[str, Path]] = []
            has_markup = False

            for _, opening in jsx.elements(root):

                tag = jsx.tag_name(opening, source) or ""

                # `<>...</>` has no name and is not content.
                if not tag:
                    continue

                if not tag[0].isupper():
                    has_markup = True
                    break

                target = imports.file_for(tag.split(".")[0])

                if target is not None:
                    own.append((tag, target))

            components = {item for item in own}

            if has_markup or len(components) != 1:
                break

            name, current = next(iter(components))

        return name, current

    @staticmethod
    def _is_fragment(microfrontend: MicroFrontend) -> bool:
        """
        Whether the micro frontend composes a page instead of being one.

        A single signal: the declared container. A permanent
        `activeWhen` was also used at one point, and it does not work —
        two applications may share the same `activeWhen` while both are
        screens, and then mounting on every URL says nothing about
        either one's role.
        """

        return bool(microfrontend.metadata.get("container"))

    def _screens(
        self,
        microfrontend: MicroFrontend,
        root_component: Path | None,
    ) -> list[Screen]:
        """
        The screens declared in any file of the micro frontend.

        Searching only from the root component finds what the system
        mounts today, and misses what is declared in a file nobody
        imports. Both are information, but only the second answers the
        question the reconstruction asks: which screens this micro
        frontend defines. If one of them is switched off, that is a
        finding for whoever reads the result, not a reason for the
        extractor to omit it.

        Where the routes live is also project organization, not a
        single-spa contract — an extractor that requires a specific
        folder is reading one repository's convention instead of the
        technology.
        """

        directory = (
            self.context.repository / microfrontend.directory
        ).resolve()

        # The files the root component actually reaches. Whatever is
        # outside this is extracted the same way, only flagged.
        alcancados = (
            Reachability(self.context).reachable_from(root_component)
            if root_component
            else set()
        )

        screens: list[Screen] = []

        seen: set[tuple[str, str]] = set()

        # Sorted so that the result does not depend on the order in which
        # the filesystem returned the paths.
        for file_path in sorted(
            path
            for path in self.context.tree.source_files()
            if directory in path.resolve().parents
        ):
            for screen in self._screens_in(
                file_path, microfrontend.id
            ):

                screen.reachable = file_path.resolve() in {
                    item.resolve() for item in alcancados
                }

                key = (screen.component, screen.route)

                if key in seen:
                    continue

                seen.add(key)

                screens.append(screen)

        return screens

    def _screens_in(
        self,
        file_path: Path,
        application_id: str,
    ) -> list[Screen]:

        root, source = self.context.reader.parse(file_path)

        imports = ImportTable(root, source, file_path)

        # Routing is an axis separate from integration: a single-spa
        # unit may be Angular, and then the screen is not in JSX.
        screens: list[Screen] = AngularRouteReader(
            self.context
        ).screens_in(file_path, application_id)

        for entry in ReactRouteReader(self.context.routes).routes_in(root, source):

            target = (
                ModuleResolver.resolve(entry.specifier, file_path)
                if entry.specifier
                else imports.file_for(entry.component)
            )

            screens.append(
                Screen(
                    component=entry.component,
                    microfrontend=application_id,
                    route=entry.route,
                    route_expression=entry.expression,
                    file=(
                        self.context.relative(target) if target else None
                    ),
                    line=entry.line,
                )
            )

        return screens
