"""
Estado compartilhado de uma reconstrução.

O repositório é varrido UMA vez. Durante essa varredura são
colhidas, juntas, as duas coisas que o resto do processo
precisa: as constantes do repositório e os `registerApplication`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
import re

from pathlib import Path

from tree_sitter import Node

from damfe.adapters.driven.reconstruction.singlespa import layout
from damfe.adapters.driven.reconstruction.ast import (
    AstReader,
    RouteConstantTable,
    SourceTree,
    SymbolIndex,
)
from damfe.adapters.driven.reconstruction.singlespa import sizing
from damfe.adapters.driven.reconstruction.templates import AngularTemplates
from damfe.domain import CodeSize


@dataclass
class Registration:
    """
    Um `registerApplication` encontrado no orquestrador.

    É a fonte de verdade do single-spa sobre quais aplicações
    existem — inclusive as que não têm pacote próprio.
    """

    name: str
    active_when: list[str]
    specifier: str | None
    declared_in: Path

    #: Como o `activeWhen` foi escrito: `literal` quando são strings
    #: ou lista de strings, `function` quando é função de atividade,
    #: `absent` quando não há.
    #:
    #: A API aceita `(location) => boolean`, e função não se resolve
    #: estaticamente. O que se extrai dela são os literais de string
    #: que aparecem dentro, o que acerta os casos comuns e erra em
    #: silêncio nos demais — função sem literal devolve rota
    #: nenhuma, função que testa um literal negativamente devolve uma
    #: rota que a aplicação não possui. Quem consome precisa saber a
    #: diferença.
    active_when_form: str = "absent"

    #: `customProps` como chave -> valor, com valor vazio quando ele
    #: não é literal.
    custom_props: dict[str, str] = field(default_factory=dict)

    #: Arquivo de entrada, quando já se sabe qual é.
    #:
    #: Preenchido pela descoberta de baixo para cima, que parte do
    #: arquivo que exporta os ciclos de vida em vez de partir do
    #: registro. Nesse caminho não há especificador a resolver: o
    #: arquivo É o ponto de partida.
    entrypoint: Path | None = None


@dataclass
class ScanContext:

    repository: Path
    tree: SourceTree
    reader: AstReader
    routes: RouteConstantTable
    registrations: list[Registration] = field(default_factory=list)
    packages: dict[str, Path] = field(default_factory=dict)

    #: aplicação -> rotas declaradas em template de layout
    layout_routes: dict[str, list[str]] = field(default_factory=dict)

    #: arquivo de layout -> (aplicação -> rotas). Quem declara o
    #: layout é o orquestrador das aplicações que ele nomeia.
    layouts: dict[Path, dict[str, list[str]]] = field(default_factory=dict)

    #: caminho -> (linhas físicas, linhas de código)
    measurements: dict[Path, tuple[int, int]] = field(default_factory=dict)

    _templates: AngularTemplates | None = field(default=None, repr=False)

    _symbols: SymbolIndex | None = field(default=None, repr=False)

    @classmethod
    def build(cls, repository: Path) -> "ScanContext":

        tree = SourceTree(repository)

        context = cls(
            repository=repository,
            tree=tree,
            reader=AstReader(),
            routes=RouteConstantTable(),
        )

        context.packages = context._index_packages()

        context._scan()

        context.layouts.update(layout.layouts(tree))

        for declared in context.layouts.values():
            for name, routes in declared.items():
                context.layout_routes.setdefault(name, []).extend(routes)

        context.layout_routes = {
            name: sorted(set(routes))
            for name, routes in context.layout_routes.items()
        }

        context.routes.resolve_pending()

        return context

    def relative(self, path: Path) -> str:
        return self.tree.relative(path)

    def layout_routes_of(self, name: str) -> list[str] | None:
        """
        As rotas que o layout dá a uma aplicação, ou `None` se ele não a nomeia.

        O layout nomeia a aplicação pelo especificador do import map,
        e a unidade se chama pelo `package.json`. Quando os dois
        coincidem, a ligação é direta. Quando não, a convenção do
        single-spa é o especificador ser `@org/<pacote>`: compara-se o
        nome sem o escopo. Semelhança além disso — prefixos, sufixos —
        seria adivinhar, e fica de fora.
        """

        if name in self.layout_routes:
            return self.layout_routes[name]

        wanted = unscoped(name)

        matches = [
            routes
            for declared, routes in self.layout_routes.items()
            if unscoped(declared) == wanted
        ]

        # Dois especificadores de escopos diferentes com o mesmo nome:
        # ambíguo, e nenhum dos dois é escolhido.
        return matches[0] if len(matches) == 1 else None

    def templates(self) -> AngularTemplates:
        """
        A ligação por template entre componentes, indexada uma vez.

        Preguiçosa: só quem pergunta pelo alcance precisa dela, e o
        índice lê todo arquivo que declara componente.
        """

        if self._templates is None:
            self._templates = AngularTemplates(
                self.reader, list(self.tree.source_files())
            )

        return self._templates

    def symbols(self) -> SymbolIndex:
        """Funções, exports e a quem cada chamada se refere — lidos sob demanda."""

        if self._symbols is None:
            self._symbols = SymbolIndex(self.reader)

        return self._symbols

    def size_of(self, directory: Path) -> "CodeSize":
        """Soma as medições dos arquivos sob um diretório."""

        return sizing.total(
            [
                measurement
                for path, measurement in self.measurements.items()
                if directory in path.parents
            ]
        )

    def package_dir(self, file_path: Path) -> Path:

        directory = file_path.parent

        # O segundo teste para na raiz do disco: caminho resolvido por
        # link simbólico pode não ter o repositório como ancestral.
        while directory != self.repository and directory != directory.parent:

            if (directory / "package.json").is_file():
                return directory

            directory = directory.parent

        return self.repository

    def _index_packages(self) -> dict[str, Path]:

        index: dict[str, Path] = {}

        for manifest_file in self.tree.manifests():

            try:
                manifest = json.loads(
                    manifest_file.read_text(encoding="utf-8")
                )
            except Exception:
                continue

            name = manifest.get("name")

            if name:
                index.setdefault(name, manifest_file.parent)

        return index

    def _scan(self) -> None:

        for file_path in self.tree.source_files():

            try:
                root, source = self.reader.parse(file_path)
            except Exception:
                continue

            self.routes.index_file(root, source)

            self.measurements[file_path] = sizing.measure(root, source)

            # A forma JavaScript do layout mora no código, não no
            # template, então é aqui que ela é colhida.
            declared = layout.routes_from_construct(root, source, AstReader)

            if declared:
                self.layouts[file_path] = declared

            self.registrations.extend(
                self._registrations(root, source, file_path)
            )

    def _registrations(
        self,
        root: Node,
        source: bytes,
        file_path: Path,
    ) -> list[Registration]:

        found: list[Registration] = []

        for node in AstReader.find_all(root, "call_expression"):

            function = node.child_by_field_name("function")

            if not function:
                continue

            if AstReader.text(function, source) != "registerApplication":
                continue

            registration = self._registration(node, source, file_path)

            if registration:
                found.append(registration)

        return found

    def _registration(
        self,
        node: Node,
        source: bytes,
        file_path: Path,
    ) -> Registration | None:
        """
        Lê um `registerApplication` nas duas formas aceitas:

            registerApplication({ name, app, activeWhen })
            registerApplication(name, loadingFn, activeWhen)
        """

        arguments = node.child_by_field_name("arguments")

        if not arguments:
            return None

        parts = [
            child
            for child in arguments.named_children
            if child.type != "comment"
        ]

        if not parts:
            return None

        if parts[0].type == "object":
            name, active_when, loader, form, custom_props = (
                self._object_form(parts[0], source)
            )
        else:
            name, active_when, loader, form, custom_props = (
                self._positional_form(parts, source)
            )

        if not name:
            return None

        return Registration(
            name=name,
            active_when=active_when,
            specifier=(
                self._loader_specifier(loader, source) if loader else None
            ),
            declared_in=file_path,
            active_when_form=form,
            custom_props=custom_props,
        )

    def _object_form(
        self,
        node: Node,
        source: bytes,
    ) -> tuple[str | None, list[str], Node | None, str, dict[str, str]]:

        name: str | None = None
        active_when: list[str] = []
        loader: Node | None = None
        form = "absent"
        custom_props: dict[str, str] = {}

        for pair in node.named_children:

            if pair.type != "pair":
                continue

            key_node = pair.child_by_field_name("key")
            value_node = pair.child_by_field_name("value")

            if not key_node or not value_node:
                continue

            key = AstReader.strip_quotes(AstReader.text(key_node, source))

            if key == "name":
                name = self._literal_name(value_node, source)

            elif key == "activeWhen":
                active_when, form = self._active_when(value_node, source)

            elif key == "app":
                loader = value_node

            elif key == "customProps":
                custom_props = self._property_names(value_node, source)

        return name, active_when, loader, form, custom_props

    def _positional_form(
        self,
        parts: list[Node],
        source: bytes,
    ) -> tuple[str | None, list[str], Node | None, str, dict[str, str]]:

        name = self._literal_name(parts[0], source)

        loader = parts[1] if len(parts) > 1 else None

        active_when, form = (
            self._active_when(parts[2], source)
            if len(parts) > 2
            else ([], "absent")
        )

        custom_props = (
            self._property_names(parts[3], source) if len(parts) > 3 else {}
        )

        return name, active_when, loader, form, custom_props

    @staticmethod
    def _literal_name(node: Node, source: bytes) -> str | None:
        """
        O nome da aplicação, só quando escrito como texto.

        `registerApplication(appName, ...)` dentro de um laço registra
        o que vier em tempo de execução. Tomar o texto do identificador
        como nome criava uma aplicação chamada `appName`. Sem nome
        literal o registro é descartado, e a descoberta pelos ciclos
        de vida acha a unidade pelo próprio pacote.
        """

        if node.type == "string":
            return AstReader.strip_quotes(AstReader.text(node, source)) or None

        if node.type == "template_string" and not any(
            child.type == "template_substitution" for child in node.named_children
        ):
            return AstReader.strip_quotes(AstReader.text(node, source)) or None

        return None

    #: Formas de função de atividade que se resolvem estaticamente.
    #:
    #: A API aceita `(location) => boolean`, e função qualquer não se
    #: resolve. Mas as que aparecem em código real são poucas e têm
    #: forma fixa, e reconhecê-las é a diferença entre extrair a rota
    #: certa e varrer literais torcendo para acertar.
    ACTIVITY_SHAPES = (
        # (l) => l.pathname.startsWith("/users")
        r"""\.startsWith\(\s*["'`](?P<r>[^"'`]+)["'`]""",
        # (l) => l.pathname === "/users"
        r"""pathname\s*={2,3}\s*["'`](?P<r>[^"'`]+)["'`]""",
        # (l) => l.pathname.includes("/users")
        r"""\.includes\(\s*["'`](?P<r>[^"'`]+)["'`]""",
        # pathToActiveWhen("/users")
        r"""pathToActiveWhen\(\s*["'`](?P<r>[^"'`]+)["'`]""",
    )

    def _active_when(
        self,
        node: Node,
        source: bytes,
    ) -> tuple[list[str], str]:
        """
        As rotas do `activeWhen`, e como elas foram obtidas.

        `literal` quando são strings ou lista de strings, e aí não há
        o que interpretar. `function` quando é função de atividade de
        forma reconhecida — `startsWith`, comparação de `pathname`,
        `includes`, `pathToActiveWhen` —, que se resolve com a mesma
        confiança de um literal. `opaque` quando é função de forma
        desconhecida: aí sobram os literais de string que houver
        dentro, que podem não ser rota nenhuma.
        """

        FUNCTIONS = {
            "arrow_function",
            "function_expression",
            "function_declaration",
            "identifier",
            "call_expression",
        }

        if node.type == "array":

            routes: list[str] = []
            forms: set[str] = set()

            for child in node.named_children:

                found, form = self._active_when(child, source)

                routes.extend(found)
                forms.add(form)

            for level in ("opaque", "function", "literal"):
                if level in forms:
                    return routes, level

            return routes, "absent"

        if node.type not in FUNCTIONS:
            return self._string_literals(node, source), "literal"

        text = AstReader.text(node, source)

        recognised = []

        for shape in self.ACTIVITY_SHAPES:
            recognised.extend(
                found.group("r") for found in re.finditer(shape, text)
            )

        if recognised:
            return sorted(set(recognised)), "function"

        return self._string_literals(node, source), "opaque"

    #: Nós cujo texto é o próprio valor.
    LITERALS = {"string", "number", "true", "false", "null"}

    @classmethod
    def _property_names(cls, node: Node, source: bytes) -> dict[str, str]:
        """
        As chaves de um literal de objeto, e os valores que forem
        estáticos.

        Valor literal é configuração escrita à mão e diz algo sobre o
        sistema. Valor que é função ou variável é dado montado em
        tempo de execução, e aí só a chave sobrevive — registrada com
        valor vazio, porque saber que a chave existe já é informação.
        """

        found: dict[str, str] = {}

        for pair in node.named_children:

            # `customProps: { store }` — a forma abreviada também é
            # chave, e costuma ser justamente a do objeto compartilhado.
            if pair.type == "shorthand_property_identifier":
                found[AstReader.text(pair, source)] = ""
                continue

            if pair.type != "pair":
                continue

            key_node = pair.child_by_field_name("key")
            value_node = pair.child_by_field_name("value")

            if not key_node:
                continue

            key = AstReader.strip_quotes(AstReader.text(key_node, source))

            value = ""

            if value_node and value_node.type in cls.LITERALS:
                value = AstReader.strip_quotes(
                    AstReader.text(value_node, source)
                )

            found[key] = value

        return dict(sorted(found.items()))

    @staticmethod
    def _string_literals(node: Node, source: bytes) -> list[str]:

        return [
            AstReader.strip_quotes(AstReader.text(literal, source))
            for literal in AstReader.find_all(node, "string")
        ]

    @staticmethod
    def _loader_specifier(node: Node, source: bytes) -> str | None:
        """
        Extrai o módulo carregado pelo `app`:

            () => System.import("@org/mfe-users")
            () => import("./monolito")
            "@org/mfe-users"
        """

        if node.type in {"string", "template_string"}:
            return AstReader.strip_quotes(AstReader.text(node, source))

        for call in AstReader.find_all(node, "call_expression"):

            function = call.child_by_field_name("function")

            if not function:
                continue

            text = AstReader.text(function, source)

            if text != "import" and not text.endswith(".import"):
                continue

            arguments = call.child_by_field_name("arguments")

            if not arguments:
                continue

            for child in arguments.named_children:

                if child.type in {"string", "template_string"}:
                    return AstReader.strip_quotes(
                        AstReader.text(child, source)
                    )

        return None


def unscoped(name: str) -> str:
    """`@org/Meu_App` → `meu-app`: o nome do pacote sem o escopo."""

    return name.rpartition("/")[2].lower().replace("_", "-")
