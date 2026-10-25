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

        #: unidade -> caminhos publicados, sem o "./"
        self.catalog = {
            item.id: {
                fragment.name.lstrip("./") for fragment in item.fragments
            }
            for item in microfrontends
        }

        self.ownership = Ownership(context.repository, microfrontends)

        self.by_id = {item.id: item for item in microfrontends}

        #: apelido local do remoto -> unidade, por quem declarou
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

                placement = self.containers.get(render.file, Placement())

                render.screens = [exact] if exact else placement.screens
                render.fragments = placement.fragments

        return sorted(
            found,
            key=lambda item: (item.consumer, item.provider, item.fragment),
        )

    def _composed(self, item: Composition) -> bool:
        """
        Se o import acontece no sistema composto.

        Um remoto tem duas portas de entrada: os módulos que publica,
        que são o que o hospedeiro carrega, e o próprio arquivo de
        entrada, que só roda quando ele é aberto sozinho, em
        desenvolvimento. Import alcançável só pela segunda nunca chega
        à página do sistema — e contá-lo fazia uma biblioteca de
        componentes, usada apenas no `main.tsx` de cada remoto, parecer
        dependida por todos.

        Vale só para remoto (quem publica algo). Hospedeiro e unidade
        sem publicação não têm essa distinção, e aí o import fica.
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

        # Import de remoto fora de qualquer unidade não liga dois
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
