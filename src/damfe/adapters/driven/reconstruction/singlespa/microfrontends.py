"""
Construção das aplicações a partir dos `registerApplication`.

Fragmentos são os exports do entrypoint que não fazem parte do
contrato de lifecycle do single-spa. Telas são as `<Route>`
declaradas pelo `rootComponent`.
"""

from __future__ import annotations

import json
import re

from pathlib import Path

from tree_sitter import Node

from damfe.domain import Fragment, MicroFrontend, Screen
from damfe.adapters.driven.reconstruction.routers import (
    ReactRouteReader,
    AngularRouteReader,
)
from damfe.adapters.driven.reconstruction.ast import AstReader, ImportTable, ModuleResolver
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

        # Sob single-spa-layout as rotas não estão no registro: elas
        # vivem no template, e o registro fica sem activeWhen algum.
        if not microfrontend.routes:

            declared = self.context.layout_routes_of(registration.name)

            if declared:
                microfrontend.routes = declared
                microfrontend.metadata["routes_from"] = "single-spa-layout"

        # Terceira fonte, a do próprio Angular: o single-spa-angular
        # manda declarar `APP_BASE_HREF` com o prefixo em que a
        # aplicação é montada, para que o roteador interno funcione
        # sob ele. É o `activeWhen` escrito do lado da aplicação — e
        # existe mesmo quando o orquestrador não está no repositório.
        if not microfrontend.routes:

            base = self._base_href(self.context.package_dir(entrypoint))

            if base:
                microfrontend.routes = [base]
                microfrontend.metadata["routes_from"] = "APP_BASE_HREF"

        # A forma do activeWhen viaja junto: rota vinda de função de
        # atividade não tem a mesma confiança de rota literal, e quem
        # lê o artefato precisa poder distinguir.
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

        if registration.entrypoint:
            return registration.entrypoint

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

    def _base_href(self, directory: Path) -> str | None:
        """
        O prefixo de `{ provide: APP_BASE_HREF, useValue: "/x/" }`.

        Só valor literal e único: mais de um prefixo distinto no mesmo
        pacote não diz qual é o da montagem. `/` também não serve —
        diz que a aplicação está na raiz, não que é dona dela.
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

                # Só as variáveis que a própria declaração cria. Descer
                # na árvore inteira pegava também as locais de dentro
                # de funções exportadas — o `let el` de
                # `export function domElementGetter() {...}` virava
                # fragmento.
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
                # A terceira forma, e a que os adaptadores de Angular
                # geram. Sem ela, uma unidade que exporta os ciclos de
                # vida um a um não é reconhecida como micro frontend, e
                # um componente exportado assim não é reconhecido como
                # fragmento.
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
        O elemento do shell em que este micro frontend é montado.

        `domElementGetter` é como o single-spa deixa a aplicação
        escolher onde aparecer, e `domElement` é a forma direta que
        os adaptadores de framework aceitam. Declará-lo significa que o shell
        reservou um lugar no layout — `#navbar-container` —, e que
        aquilo é encaixado numa página junto de outras coisas. Quem
        não declara recebe um `div` que o single-spa anexa ao corpo,
        e ocupa a página sozinho.

        É o sinal mais forte que existe para separar composição de
        tela, e não depende de convenção de pasta nem de nome.
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
        O que o componente raiz é, quando o micro frontend não tem
        roteador próprio.

        Em single-spa o roteador é o `activeWhen`: um micro frontend
        registrado num prefixo já serve aquela rota, e roteador
        interno só faz falta para servir várias telas sob o mesmo
        prefixo. Então ausência de `<Route>` não significa ausência de
        tela — significa uma tela só.

        O sinal de que é composição, e não tela, é o contêiner
        declarado. `domElementGetter` apontando para um
        elemento do shell significa que o layout reservou um lugar
        para aquilo — ele é encaixado numa página junto de outras
        coisas. Quem não declara recebe um `div` anexado ao corpo.

        Sem ele, o componente raiz é a tela daquele
        prefixo. A rota é a do registro; não há expressão a resolver,
        porque ela não foi escrita no código da tela.
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

        microfrontend.screens = [
            Screen(
                component=name,
                microfrontend=microfrontend.id,
                route=microfrontend.routes[0] if microfrontend.routes else None,
                file=self.context.relative(root_component),
            )
        ]

    @staticmethod
    def _is_fragment(microfrontend: MicroFrontend) -> bool:
        """
        Se o micro frontend compõe uma página em vez de ser uma.

        Um sinal só: o contêiner declarado. Chegou-se a usar também
        `activeWhen` permanente, e ele não serve — duas aplicações
        podem dividir o mesmo `activeWhen` sendo as duas telas, e aí
        montar em toda URL não diz nada sobre o papel de nenhuma.
        """

        return bool(microfrontend.metadata.get("container"))

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

        # Roteamento é eixo à parte do de integração: uma unidade
        # single-spa pode ser Angular, e aí a tela não está em JSX.
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
