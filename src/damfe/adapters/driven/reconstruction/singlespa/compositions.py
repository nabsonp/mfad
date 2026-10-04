"""
Uso real de fragmentos entre aplicações.

O catálogo de fragmentos é o que dá precisão aqui: sem ele não
há como distinguir um fragmento de qualquer outro export do
mesmo pacote, nem reconhecer uma instanciação em JSX sem apelar
para convenção de nome.
"""

from __future__ import annotations

import re

from pathlib import Path

from tree_sitter import Node

from damfe.domain import (
    MicroFrontend,
    Composition,
    RenderLocation,
    SourceLocation,
)
from damfe.adapters.driven.reconstruction.ast import AstReader, ImportTable
from damfe.adapters.driven.reconstruction.singlespa import jsx
from damfe.adapters.driven.reconstruction.singlespa.context import ScanContext
from damfe.adapters.driven.reconstruction.singlespa.reachability import (
    Reachability,
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

        self.containers: dict[str, list[str]] = {}

        self.owners: dict[str, str] = {
            microfrontend.directory: microfrontend.id
            for microfrontend in microfrontends
            if microfrontend.directory
        }

    def extract(self) -> list[Composition]:

        found: list[Composition] = []

        self.containers = self._containers()

        for file_path in self.context.tree.source_files():

            try:
                root, source = self.context.reader.parse(file_path)
            except Exception:
                continue

            found.extend(self._from_file(file_path, root, source))

        for item in found:
            for render in item.renders:
                render.screens = self.containers.get(render.file, [])

        return sorted(
            found,
            key=lambda item: (
                item.consumer,
                item.provider,
                item.fragment,
            ),
        )

    def _containers(self) -> dict[str, list[str]]:
        """
        Arquivo → telas que o alcançam.

        Invertido de propósito: a extração acha a instanciação e
        precisa perguntar quem chega até ela, não o contrário.

        O fragmento raramente é instanciado no arquivo da própria
        tela. Ele costuma estar num componente que a tela usa, uma ou
        duas camadas abaixo, e perguntar só pelo arquivo devolveria
        quase nada. O fecho transitivo de imports relativos é o que
        liga uma coisa à outra — o mesmo caminho que já atribui
        chamada externa a tela.
        """

        reachability = Reachability(self.context)

        found: dict[str, list[str]] = {}

        for microfrontend in self.microfrontends:

            for screen in microfrontend.screens:

                if not screen.file:
                    continue

                origin = self.context.repository / screen.file

                if not origin.is_file():
                    continue

                for reached in reachability.reachable_from(origin):

                    found.setdefault(
                        self.context.relative(reached), []
                    ).append(screen.id)

        return {
            path: sorted(set(names)) for path, names in found.items()
        }

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

        consumer = self._owner_of(file_path)

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

            # <Parcel config={Modal} /> — o componente renderizado é
            # sempre `Parcel`, e o fragmento de verdade está na prop.
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
        """O identificador passado em `config={...}` de um `<Parcel>`."""

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
        Montagem manual de parcel: o outro jeito de compor.

        Um parcel é um componente agnóstico de framework que uma
        aplicação exporta e outra monta à mão, sem JSX:

            mountRootParcel(Modal, { domElement })
            props.mountParcel(Modal, { domElement })

        Procurar só por elemento JSX perde isso inteiro, e um sistema
        composto por parcels voltaria sem consumo de fragmento algum
        — resultado que parece válido e não é.

        O primeiro argumento é a configuração do parcel, que é o
        fragmento importado.
        """

        MOUNTS = {"mountRootParcel", "mountParcel"}

        found: dict[str, list[RenderLocation]] = {}

        for call in AstReader.find_all(root, "call_expression"):

            function = call.child_by_field_name("function")
            arguments = call.child_by_field_name("arguments")

            if not function or not arguments:
                continue

            # `mountRootParcel(...)` e `props.mountParcel(...)`
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
