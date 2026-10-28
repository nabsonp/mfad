"""
Consumption of remote modules.

The import crosses the boundary through the specifier: `app1/Botao`
means the module `./Botao` published by the unit `app1`. The name
before the slash is the remote's alias, declared in `remotes`; the rest
is the `exposes` key on the other end, without the leading `./`.

This is more precise than the single-spa equivalent, where any named
export could be a fragment. Here both ends are declared: the publisher
states it in `exposes`, the consumer states it in `remotes`, and the
import only matches when the two declarations meet.
"""

from __future__ import annotations

from pathlib import Path

from tree_sitter import Node

from mfad.domain import (
    Composition,
    MicroFrontend,
    Placement,
    RenderLocation,
    SourceLocation,
)
from mfad.adapters.driven.reconstruction.ast import ImportTable
from mfad.adapters.driven.reconstruction.singlespa import jsx
from mfad.adapters.driven.reconstruction.singlespa.context import ScanContext
from mfad.adapters.driven.reconstruction.singlespa.ownership import Ownership
from mfad.adapters.driven.reconstruction.singlespa.reachability import (
    placements,
)
from mfad.adapters.driven.reconstruction.modulefederation import specifiers


class RemoteImportExtractor:

    def __init__(
        self,
        context: ScanContext,
        microfrontends: list[MicroFrontend],
    ):
        self.context = context
        self.microfrontends = microfrontends

        #: unit -> published paths, without the "./"
        self.catalog = {
            item.id: {
                fragment.name.lstrip("./") for fragment in item.fragments
            }
            for item in microfrontends
        }

        self.ownership = Ownership(context.repository, microfrontends)

        self.by_id = {item.id: item for item in microfrontends}

        #: local alias of the remote -> unit, per declaring unit
        self.aliases = {
            item.id: {
                alias: alias
                for alias in item.metadata.get("remotes", [])
            }
            for item in microfrontends
        }

        self.containers: dict[str, Placement] = {}

    def extract(self) -> list[Composition]:

        self.containers = placements(self.context, self.microfrontends)

        found: list[Composition] = []

        for file_path in self.context.tree.source_files():

            try:
                root, source = self.context.reader.parse(file_path)
            except Exception:
                continue

            found.extend(self._from_file(file_path, root, source))

        found = [item for item in found if self._composed(item)]

        by_component = {
            (item.id, screen.component): screen.id
            for item in self.microfrontends
            for screen in item.screens
        }

        for item in found:

            # When the fragment IS the component of a route, the
            # screen is that one and only that one. Falling back to
            # reachability here would return every screen declared in
            # the same routes file, which is where they usually sit
            # together.
            #
            # The PROVIDER comes first. The route is declared in the
            # host's router, but the screen belongs to whoever
            # publishes the module, and that is where it is
            # registered. Searching only in the consumer returned
            # empty for exactly the case this rule exists to solve.
            exact = by_component.get(
                (item.provider, item.local_name)
            ) or by_component.get((item.consumer, item.local_name))

            for render in item.renders:

                placement = self.containers.get(render.file, Placement())

                render.screens = [exact] if exact else placement.screens
                render.fragments = placement.fragments

        return sorted(
            found,
            key=lambda item: (item.consumer, item.provider, item.fragment),
        )

    def _composed(self, item: Composition) -> bool:
        """
        Whether the import happens in the composed system.

        A remote has two entry points: the modules it publishes, which
        are what the host loads, and its own entry file, which only
        runs when it is opened on its own, in development. An import
        reachable only through the second never reaches the system's
        page — and counting it made a component library, used only in
        each remote's `main.tsx`, look depended on by everyone.

        Applies only to remotes (units that publish something). Hosts
        and units with nothing published have no such distinction, so
        the import stays.
        """

        consumer = self.by_id.get(item.consumer)

        if consumer is None or consumer.role == "shell" or not consumer.fragments:
            return True

        own = {fragment.id for fragment in consumer.fragments} | {
            screen.id for screen in consumer.screens
        }

        placement = self.containers.get(item.imported_at.file, Placement())

        return bool(own & (set(placement.fragments) | set(placement.screens)))

    def _from_file(
        self,
        file_path: Path,
        root: Node,
        source: bytes,
    ) -> list[Composition]:

        consumer = self.ownership.of_file(file_path)

        # A remote import outside any unit does not connect two
        # micro frontends.
        if not consumer:
            return []

        renders = self._render_sites(root, source, file_path)

        relative = self.context.relative(file_path)

        found = []

        records = [
            (record.module, record.local_name, record.line, record.code)
            for record in ImportTable.records(root, source)
        ] + self._dynamic(root, source)

        for module, local_name, line, code in records:

            provider, fragment = self._split(module)

            if not provider:
                continue

            if provider == consumer:
                continue

            found.append(
                Composition(
                    consumer=consumer,
                    provider=provider,
                    fragment=f"./{fragment}",
                    local_name=local_name,
                    imported_at=SourceLocation(
                        file=relative,
                        line=line,
                        code=code,
                    ),
                    renders=renders.get(local_name, []),
                )
            )

        return found

    @staticmethod
    def _dynamic(
        root: Node,
        source: bytes,
    ) -> list[tuple[str, str, int, str]]:
        """
        `const Pharmacy = lazy(() => import("hs-pharmacy/Pharmacy"))`.

        This is how a host loads a remote page, not via a static
        import: the point of Module Federation is to fetch the code on
        demand, and the framework requires a lazy boundary for that.
        Reading only static imports finds the shared libraries and
        misses exactly the pages — the consumption that defines the
        system.
        """

        return specifiers.dynamic_imports(root, source)

    def _split(self, module: str) -> tuple[str | None, str]:
        """`app1/Botao` → (`app1`, `Botao`), when both ends match."""

        return specifiers.split(module, self.catalog)

    def _render_sites(
        self,
        root: Node,
        source: bytes,
        file_path: Path,
    ) -> dict[str, list[RenderLocation]]:

        relative = self.context.relative(file_path)

        sites: dict[str, list[RenderLocation]] = {}

        for element, opening in jsx.elements(root):

            tag = jsx.tag_name(opening, source)

            if not tag:
                continue

            sites.setdefault(tag, []).append(
                RenderLocation(
                    file=relative,
                    line=element.start_point.row + 1,
                    props=jsx.prop_names(opening, source),
                )
            )

        return sites
