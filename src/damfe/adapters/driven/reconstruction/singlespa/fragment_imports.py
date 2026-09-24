"""
Uso real de fragmentos entre aplicações.

O catálogo de fragmentos é o que dá precisão aqui: sem ele não
há como distinguir um fragmento de qualquer outro export do
mesmo pacote, nem reconhecer uma instanciação em JSX sem apelar
para convenção de nome.
"""

from __future__ import annotations

from pathlib import Path

from tree_sitter import Node

from damfe.domain import (
    MicroFrontend,
    FragmentImport,
    RenderSite,
    SourceLocation,
)
from damfe.adapters.driven.reconstruction.ast import ImportTable
from damfe.adapters.driven.reconstruction.singlespa import jsx
from damfe.adapters.driven.reconstruction.singlespa.context import ScanContext


class FragmentImportExtractor:

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

        self.owners: dict[str, str] = {
            microfrontend.directory: microfrontend.id
            for microfrontend in microfrontends
            if microfrontend.directory
        }

    def extract(self) -> list[FragmentImport]:

        found: list[FragmentImport] = []

        for file_path in self.context.tree.source_files():

            try:
                root, source = self.context.reader.parse(file_path)
            except Exception:
                continue

            found.extend(self._from_file(file_path, root, source))

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
    ) -> list[FragmentImport]:

        records = [
            record
            for record in ImportTable.records(root, source)
            if record.imported_name
            in self.catalog.get(record.module, set())
        ]

        if not records:
            return []

        consumer = self._owner_of(file_path)

        renders = self._render_sites(root, source, file_path)

        relative = self.context.relative(file_path)

        return [
            FragmentImport(
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

    def _owner_of(self, file_path: Path) -> str:

        try:
            relative = file_path.relative_to(self.context.repository)
        except ValueError:
            return "?"

        if not relative.parts:
            return "?"

        directory = relative.parts[0]

        return self.owners.get(directory, directory)

    def _render_sites(
        self,
        root: Node,
        source: bytes,
        file_path: Path,
    ) -> dict[str, list[RenderSite]]:

        relative = self.context.relative(file_path)

        sites: dict[str, list[RenderSite]] = {}

        for element, opening in jsx.elements(root):

            tag = jsx.tag_name(opening, source)

            if not tag:
                continue

            sites.setdefault(tag, []).append(
                RenderSite(
                    file=relative,
                    line=element.start_point.row + 1,
                    props=jsx.prop_names(opening, source),
                )
            )

        return sites
