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
from damfe.adapters.driven.reconstruction.ast import AstReader, ImportTable
from damfe.adapters.driven.reconstruction.singlespa import jsx
from damfe.adapters.driven.reconstruction.singlespa.context import ScanContext
from damfe.adapters.driven.reconstruction.singlespa.reachability import (
    Reachability,
)
from damfe.adapters.driven.reconstruction.modulefederation import specifiers


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
            #
            # O PROVEDOR vem primeiro. A rota é declarada no roteador
            # de quem hospeda, mas a tela pertence a quem publica o
            # módulo, e é lá que ela está registrada. Procurar só no
            # consumidor devolvia vazio para exatamente o caso que
            # esta regra existe para resolver.
            exact = by_component.get(
                (item.provider, item.local_name)
            ) or by_component.get((item.consumer, item.local_name))

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
                FragmentImport(
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

        É assim que um host carrega página remota, e não como import
        estático: o ponto de Module Federation é buscar o código na
        hora, e o framework exige uma fronteira preguiçosa para isso.
        Ler só o import estático encontra as bibliotecas compartilhadas
        e perde exatamente as páginas — o consumo que define o sistema.
        """

        return specifiers.dynamic_imports(root, source)

    def _split(self, module: str) -> tuple[str | None, str]:
        """`app1/Botao` → (`app1`, `Botao`), quando as duas pontas batem."""

        return specifiers.split(module, self.catalog)

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
