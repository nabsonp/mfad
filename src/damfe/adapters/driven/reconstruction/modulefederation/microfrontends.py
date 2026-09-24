"""
As unidades federadas e o que cada uma contém.

A diferença para single-spa está aqui, e só aqui. Lá existe um
orquestrador que declara todo mundo; aqui cada unidade se declara, e
o sistema é o que emerge quando as declarações são lidas juntas.

Três consequências que mudam a extração:

Não há `activeWhen`. Module Federation resolve carregamento de código
remoto e não diz nada sobre URL. As rotas de uma unidade são as do
roteador dela, e só existem se ela tiver um.

Não há papel de shell declarado. Quem hospeda e quem é hospedado não
são exclusivos: uma unidade pode consumir remotos e ser consumida ao
mesmo tempo. O que se pode afirmar é quem consome sem ser consumido,
e é isso que se marca.

Fragmento é o `exposes`, que é declaração explícita — melhor sinal do
que qualquer export nomeado, que é o que sobra no single-spa.
"""

from __future__ import annotations

from pathlib import Path

from damfe.domain import Fragment, MicroFrontend, Screen
from damfe.adapters.driven.reconstruction.ast import AstReader, ImportTable
from damfe.adapters.driven.reconstruction.singlespa import jsx
from damfe.adapters.driven.reconstruction.singlespa.context import ScanContext
from damfe.adapters.driven.reconstruction.modulefederation import config


class FederatedBuilder:

    def __init__(self, context: ScanContext, federations: list):
        self.context = context
        self.federations = federations

    def build(self) -> list[MicroFrontend]:

        consumed = {
            remote
            for federation in self.federations
            for remote in federation.remotes
        }

        found = []

        for federation in self.federations:

            found.append(self._one(federation, consumed))

        return found

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

        # Forma de biblioteca: o módulo exposto só reexporta, em vez
        # de definir o que publica. A unidade entrega um catálogo de
        # peças, não uma peça.
        #
        # É sinal, não classificação. Biblioteca que exponha componente
        # por componente não tem barril, e remoto pode expor um barril
        # de páginas — o formato acerta o caso comum e não prova a
        # natureza da coisa. Quem decide se aquilo é biblioteca é quem
        # lê, e é por isso que o número fica registrado em vez de mudar
        # o comportamento das regras.
        if barrels:
            microfrontend.metadata["reexports"] = barrels

        if federation.remotes:
            microfrontend.metadata["remotes"] = sorted(federation.remotes)

        if federation.shared:
            microfrontend.metadata["shared"] = federation.shared

        # Consome remotos e não é consumida por ninguém: é a ponta da
        # composição, que é o mais próximo de um shell que Module
        # Federation define. Quando todos se consomem, ninguém é.
        if federation.remotes and federation.name not in consumed:
            microfrontend.role = "shell"
            microfrontend.mounts = sorted(federation.remotes)

        microfrontend.screens = self._screens(directory, federation.name)

        microfrontend.routes = sorted(
            {screen.route for screen in microfrontend.screens if screen.route}
        )

        return microfrontend

    def _resolve(self, directory: Path, target: str) -> str | None:
        """O arquivo interno que um `exposes` aponta."""

        if not target:
            return None

        base = (directory / target).resolve()

        for candidate in [base] + [
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
        Quantos nomes o módulo reexporta sem definir.

        `export { Card } from "./ui/card"` conta; `export default
        function Pharmacy()` não. Zero significa que o módulo define o
        que publica.
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
        As telas declaradas pelo roteador da própria unidade.

        Sem `activeWhen` não há rota vinda do registro, então tela
        aqui só existe quando a unidade tem roteador. Uma unidade que
        só publica componentes não tem tela nenhuma, e isso é o
        resultado correto — ela não responde por URL alguma.
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

            for element, opening in jsx.elements(root):

                if jsx.tag_name(opening, source) != "Route":
                    continue

                attributes = jsx.attributes(opening, source)

                component = jsx.component_name(
                    attributes.get("element", "")
                )

                if not component:
                    continue

                route = self.context.routes.resolve(
                    attributes.get("path", "")
                )

                key = (component, route or "")

                if key in seen:
                    continue

                seen.add(key)

                # O arquivo da tela é o do COMPONENTE, não o do
                # roteador. Apontar para o roteador faz toda tela
                # alcançar tudo que ele importa, e a atribuição de
                # fragmento a tela vira ruído: cada tela recebe as
                # dependências de todas as outras.
                target = imports.file_for(component)

                found.append(
                    Screen(
                        component=component,
                        microfrontend=owner,
                        route=route,
                        route_expression=attributes.get("path", ""),
                        file=(
                            self.context.relative(target)
                            if target
                            else self.context.relative(file_path)
                        ),
                        line=element.start_point.row + 1,
                    )
                )

        return found
