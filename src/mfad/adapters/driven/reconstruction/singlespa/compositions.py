"""
Actual use of fragments across applications.

The fragment catalog is what gives precision here: without it there
is no way to tell a fragment from any other export of the same
package, nor to recognize an instantiation in JSX without resorting
to naming conventions.
"""

from __future__ import annotations

import re

from pathlib import Path

from tree_sitter import Node

from mfad.domain import (
    MicroFrontend,
    Placement,
    Composition,
    RenderLocation,
    SourceLocation,
)
from mfad.adapters.driven.reconstruction.ast import AstReader, ImportTable
from mfad.adapters.driven.reconstruction.singlespa import jsx
from mfad.adapters.driven.reconstruction.singlespa.context import ScanContext
from mfad.adapters.driven.reconstruction.singlespa.ownership import Ownership
from mfad.adapters.driven.reconstruction.singlespa.reachability import (
    placements,
)


class CompositionExtractor:

    def __init__(
        self,
        context: ScanContext,
        microfrontends: list[MicroFrontend],
    ):
        self.context = context

        self.catalog: dict[str, set[str]] = {
            microfrontend.id: {
                fragment.name for fragment in microfrontend.fragments
            }
            for microfrontend in microfrontends
        }

        self.microfrontends = microfrontends

        self.containers: dict[str, Placement] = {}

        self.ownership = Ownership(context.repository, microfrontends)

    def extract(self) -> list[Composition]:

        found: list[Composition] = []

        self.containers = placements(self.context, self.microfrontends)

        for file_path in self.context.tree.source_files():

            try:
                root, source = self.context.reader.parse(file_path)
            except Exception:
                continue

            found.extend(self._from_file(file_path, root, source))

        # The fragment is rarely instantiated in the screen's own file.
        # It usually sits in a component the screen uses, one or two
        # layers below, and asking only about the file would return
        # almost nothing. The transitive closure of relative imports is
        # what links one to the other — the same path that already
        # attributes an external call to a screen.
        for item in found:
            for render in item.renders:

                placement = self.containers.get(render.file, Placement())

                render.screens = placement.screens
                render.fragments = placement.fragments

        return sorted(
            found,
            key=lambda item: (
                item.consumer,
                item.provider,
                item.fragment,
            ),
        )

    def _from_file(
        self,
        file_path: Path,
        root: Node,
        source: bytes,
    ) -> list[Composition]:

        records = [
            record
            for record in ImportTable.records(root, source)
            if record.imported_name
            in self.catalog.get(record.module, set())
        ]

        if not records:
            return []

        consumer = self.ownership.of_file(file_path)

        # A fragment import outside any unit — shared package, example —
        # does not link two micro frontends.
        if not consumer:
            return []

        renders = self._render_sites(root, source, file_path)

        relative = self.context.relative(file_path)

        return [
            Composition(
                consumer=consumer,
                provider=record.module,
                fragment=record.imported_name,
                local_name=record.local_name,
                imported_at=SourceLocation(
                    file=relative,
                    line=record.line,
                    code=record.code,
                ),
                renders=renders.get(record.local_name, []),
            )
            for record in records
        ]

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

            # <Parcel config={Modal} /> — the rendered component is
            # always `Parcel`, and the real fragment is in the prop.
            if tag.endswith("Parcel"):

                for name in self._parcel_config(opening, source):
                    sites.setdefault(name, []).append(
                        RenderLocation(
                            file=relative,
                            line=element.start_point.row + 1,
                            props=jsx.prop_names(opening, source),
                        )
                    )

        sites.update(
            self._parcel_mounts(root, source, relative, sites)
        )

        return sites

    @staticmethod
    def _parcel_config(opening: Node, source: bytes) -> list[str]:
        """The identifier passed in `config={...}` of a `<Parcel>`."""

        found = jsx.attributes(opening, source).get("config", "")

        return re.findall(r"[A-Za-z_$][\w$]*", found)[:1]

    def _parcel_mounts(
        self,
        root: Node,
        source: bytes,
        relative: str,
        sites: dict[str, list[RenderLocation]],
    ) -> dict[str, list[RenderLocation]]:
        """
        Manual parcel mounting: the other way of composing.

        A parcel is a framework-agnostic component that one application
        exports and another mounts by hand, without JSX:

            mountRootParcel(Modal, { domElement })
            props.mountParcel(Modal, { domElement })

        Looking only for JSX elements misses this entirely, and a system
        composed of parcels would come back with no fragment
        consumption at all — a result that looks valid and is not.

        The first argument is the parcel's configuration, which is the
        imported fragment.
        """

        MOUNTS = {"mountRootParcel", "mountParcel"}

        found: dict[str, list[RenderLocation]] = {}

        for call in AstReader.find_all(root, "call_expression"):

            function = call.child_by_field_name("function")
            arguments = call.child_by_field_name("arguments")

            if not function or not arguments:
                continue

            # `mountRootParcel(...)` and `props.mountParcel(...)`
            name = AstReader.text(function, source).split(".")[-1].strip()

            if name not in MOUNTS:
                continue

            parts = [
                child
                for child in arguments.named_children
                if child.type != "comment"
            ]

            if not parts:
                continue

            config = AstReader.text(parts[0], source).strip()

            if not re.fullmatch(r"[A-Za-z_$][\w$]*", config):
                continue

            found.setdefault(config, list(sites.get(config, []))).append(
                RenderLocation(
                    file=relative,
                    line=call.start_point.row + 1,
                    props=[],
                )
            )

        return found
