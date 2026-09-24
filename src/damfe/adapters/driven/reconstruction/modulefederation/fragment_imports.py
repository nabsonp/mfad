"""
Consumo de módulo remoto.

O import atravessa a fronteira pelo especificador: `app1/Botao` quer
dizer o módulo `./Botao` publicado pela unidade `app1`. O nome antes
da barra é o apelido do remoto, declarado em `remotes`; o resto é a
chave do `exposes` da outra ponta, sem o `./` inicial.

É mais preciso que o equivalente em single-spa, onde qualquer export
nomeado podia ser fragmento. Aqui as duas pontas são declaradas: quem
publica diz em `exposes`, quem consome diz em `remotes`, e o import
só casa quando as duas declarações se encontram.
"""

from __future__ import annotations

from pathlib import Path

from tree_sitter import Node

from damfe.domain import (
    FragmentImport,
    MicroFrontend,
    RenderSite,
    SourceLocation,
)
from damfe.adapters.driven.reconstruction.ast import ImportTable
from damfe.adapters.driven.reconstruction.singlespa import jsx
from damfe.adapters.driven.reconstruction.singlespa.context import ScanContext
from damfe.adapters.driven.reconstruction.singlespa.reachability import (
    Reachability,
)


class RemoteImportExtractor:

    def __init__(
        self,
        context: ScanContext,
        microfrontends: list[MicroFrontend],
    ):
        self.context = context
        self.microfrontends = microfrontends

        #: unidade -> caminhos publicados, sem o "./"
        self.catalog = {
            item.id: {
                fragment.name.lstrip("./") for fragment in item.fragments
            }
            for item in microfrontends
        }

        self.owners = {
            item.directory: item.id
            for item in microfrontends
            if item.directory
        }

        #: apelido local do remoto -> unidade, por quem declarou
        self.aliases = {
            item.id: {
                alias: alias
                for alias in item.metadata.get("remotes", [])
            }
            for item in microfrontends
        }

        self.containers: dict[str, list[str]] = {}

    def extract(self) -> list[FragmentImport]:

        self.containers = self._containers()

        found: list[FragmentImport] = []

        for file_path in self.context.tree.source_files():

            try:
                root, source = self.context.reader.parse(file_path)
            except Exception:
                continue

            found.extend(self._from_file(file_path, root, source))

        by_component = {
            (item.id, screen.component): screen.id
            for item in self.microfrontends
            for screen in item.screens
        }

        for item in found:

            # Quando o fragmento É o componente de uma rota, a tela
            # é aquela e só aquela. Cair na alcançabilidade aqui
            # devolveria todas as telas declaradas no mesmo arquivo
            # de rotas, que é onde elas costumam estar juntas.
            exact = by_component.get((item.consumer, item.local_name))

            for render in item.renders:

                render.screens = (
                    [exact]
                    if exact
                    else self.containers.get(render.file, [])
                )

        return sorted(
            found,
            key=lambda item: (item.consumer, item.provider, item.fragment),
        )

    def _from_file(
        self,
        file_path: Path,
        root: Node,
        source: bytes,
    ) -> list[FragmentImport]:

        consumer = self._owner_of(file_path)

        renders = self._render_sites(root, source, file_path)

        relative = self.context.relative(file_path)

        found = []

        for record in ImportTable.records(root, source):

            provider, fragment = self._split(record.module)

            if not provider:
                continue

            if provider == consumer:
                continue

            found.append(
                FragmentImport(
                    consumer=consumer,
                    provider=provider,
                    fragment=f"./{fragment}",
                    local_name=record.local_name,
                    imported_at=SourceLocation(
                        file=relative,
                        line=record.line,
                        code=record.code,
                    ),
                    renders=renders.get(record.local_name, []),
                )
            )

        return found

    def _split(self, module: str) -> tuple[str | None, str]:
        """
        `app1/Botao` → (`app1`, `Botao`), quando as duas pontas batem.

        Casa o prefixo mais longo primeiro, porque o nome da unidade
        pode conter barra — `@org/app1/Botao` é a unidade `@org/app1`
        publicando `./Botao`.
        """

        parts = module.split("/")

        for cut in range(len(parts) - 1, 0, -1):

            candidate = "/".join(parts[:cut])
            rest = "/".join(parts[cut:])

            if rest in self.catalog.get(candidate, set()):
                return candidate, rest

        return None, ""

    def _owner_of(self, file_path: Path) -> str:

        relative = self.context.relative(file_path)

        best = ""
        owner = ""

        for directory, name in self.owners.items():

            if relative.startswith(directory) and len(directory) > len(best):
                best, owner = directory, name

        return owner

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

    def _containers(self) -> dict[str, list[str]]:
        """Arquivo → telas que o alcançam. Ver a regra em US-26."""

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

        return {path: sorted(set(names)) for path, names in found.items()}
