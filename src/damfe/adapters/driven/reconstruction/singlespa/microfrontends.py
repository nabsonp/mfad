"""
Construção das aplicações a partir dos `registerApplication`.

Fragmentos são os exports do entrypoint que não fazem parte do
contrato de lifecycle do single-spa. Telas são as `<Route>`
declaradas pelo `rootComponent`.
"""

from __future__ import annotations

import json

from pathlib import Path

from tree_sitter import Node

from damfe.domain import Fragment, MicroFrontend, Screen
from damfe.adapters.driven.reconstruction.ast import AstReader, ImportTable, ModuleResolver
from damfe.adapters.driven.reconstruction.singlespa import jsx
from damfe.adapters.driven.reconstruction.singlespa.context import Registration, ScanContext
from damfe.adapters.driven.reconstruction.singlespa.reachability import (
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

        # Aplicação registrada cujo entrypoint não resolve segue
        # sendo um nó do grafo. Sumir é pior que aparecer incompleta.
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

        for name, line in exported:

            target = imports.file_for(name)

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

        root_component = self._root_component_file(root, source, imports)

        microfrontend.screens = self._screens(microfrontend, root_component)

        if not microfrontend.screens and root_component:
            self._root_as_fragment(root_component, microfrontend)

        return microfrontend

    def _entrypoint_for(
        self,
        registration: Registration,
    ) -> Path | None:
        """
        O arquivo de entrada do micro frontend registrado.

        Duas vias, nesta ordem. O índice de pacotes resolve o
        especificador do import map — `@org/mfe-x` — para o diretório
        que declara aquele nome no `package.json`, que é a via
        confiável. A convenção de nome é o recurso quando o pacote não
        está no repositório analisado.

        Aplicação registrada sem pacote próprio existe: o shell pode
        declarar ciclos de vida inline. Devolver `None` aqui é
        resposta legítima, e `build` a mantém no grafo marcada como
        não resolvida.
        """

        specifier = registration.specifier

        if not specifier:
            return None

        # Caminho relativo: o shell carrega o módulo do próprio
        # repositório, sem pacote publicado. É assim que um monolito
        # sendo migrado entra no grafo — ele é aplicação registrada
        # como qualquer outra, e some se só olharmos o import map.
        if specifier.startswith("."):
            return ModuleResolver.resolve(
                specifier, registration.declared_in
            )

        directory = self.context.packages.get(specifier)

        if directory:

            found = self._by_convention(directory, specifier)

            if found:
                return found

            # Pacote encontrado, entrada fora da convenção: o campo
            # `main`/`module` do manifesto é a declaração do próprio
            # projeto sobre onde ele começa.
            return self._from_manifest(directory)

        for candidate in self.context.tree.manifests():

            found = self._by_convention(candidate.parent, specifier)

            if found:
                return found

        return None

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
        """O que o `package.json` declara como ponto de partida."""

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
        O que o arquivo de entrada expõe.

        Devolve dois conjuntos. Os ciclos de vida — `bootstrap`,
        `mount`, `unmount`, `update` — dizem que aquilo é um micro
        frontend do single-spa. Todo o resto que sai por `export` é
        fragmento: componente publicado para outro micro frontend
        consumir.
        """

        lifecycles: list[str] = []
        exported: list[tuple[str, int]] = []

        for node in AstReader.find_all(root, "export_statement"):

            # export const { bootstrap, mount, unmount } = lifecycles;
            declaration = node.child_by_field_name("declaration")

            if declaration:

                for pattern in AstReader.find_all(
                    declaration,
                    "shorthand_property_identifier_pattern",
                ):
                    name = AstReader.text(pattern, source)

                    if name in LIFECYCLE_NAMES:
                        lifecycles.append(name)

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

    def _root_as_fragment(
        self,
        root_component: Path,
        microfrontend: MicroFrontend,
    ) -> None:
        """
        O componente raiz como fragmento, quando não há tela alguma.

        Um micro frontend sem rota nenhuma não serve tela: ele entrega
        um pedaço de interface que o shell monta — cromo como barra de
        navegação e rodapé, ou um bloco que compõe uma página. O que
        ele expõe é o `rootComponent`, e é isso que os outros veem.

        Chamar esse componente de tela seria afirmar que o micro
        frontend responde por uma rota, o que não é verdade: barra de
        navegação registrada com `activeWhen: ["/"]` monta em todas as
        URLs e não é dona de nenhuma.

        A distinção entre cromo e bloco de página não é decidível
        daqui, e não é feita: os dois são fragmento.
        """

        name = root_component.stem

        if any(item.name == name for item in microfrontend.fragments):
            return

        microfrontend.fragments.append(
            Fragment(
                name=name,
                microfrontend=microfrontend.id,
                file=self.context.relative(root_component),
            )
        )

    def _screens(
        self,
        microfrontend: MicroFrontend,
        root_component: Path | None,
    ) -> list[Screen]:
        """
        As telas declaradas em qualquer arquivo do micro frontend.

        Procurar só a partir do componente raiz encontra o que o
        sistema monta hoje, e perde o que está declarado num arquivo
        que ninguém importa. Os dois são informação, mas só o segundo
        responde à pergunta que a reconstrução faz: quais telas este
        micro frontend define. Se uma delas está desligada, isso é
        achado para quem lê o resultado, não motivo para o extrator
        omiti-la.

        Onde as rotas moram também é organização de projeto, não
        contrato do single-spa — um extrator que exija uma pasta
        específica está lendo a convenção de um repositório em vez da
        tecnologia.
        """

        directory = (
            self.context.repository / microfrontend.directory
        ).resolve()

        # Os arquivos que o componente raiz de fato alcança. O que
        # estiver fora disto é extraído do mesmo jeito, só marcado.
        alcancados = (
            Reachability(self.context).reachable_from(root_component)
            if root_component
            else set()
        )

        screens: list[Screen] = []

        seen: set[tuple[str, str]] = set()

        # Ordenado para que o resultado não dependa da ordem em que o
        # sistema de arquivos devolveu os caminhos.
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

        screens: list[Screen] = []

        for element, opening in jsx.elements(root):

            if jsx.tag_name(opening, source) != "Route":
                continue

            found = jsx.attributes(opening, source)

            element_expression = found.get("element")

            if not element_expression:
                continue

            component = jsx.component_name(element_expression)

            if not component:
                continue

            expression = found.get("path", "")

            target = imports.file_for(component)

            screens.append(
                Screen(
                    component=component,
                    microfrontend=application_id,
                    route=(
                        self.context.routes.resolve(expression)
                        if expression
                        else None
                    ),
                    route_expression=expression,
                    file=(
                        self.context.relative(target) if target else None
                    ),
                    line=element.start_point.row + 1,
                )
            )

        return screens
