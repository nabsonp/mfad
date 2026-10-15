"""
Navegação entre aplicações.

Não existe API padrão de navegação no single-spa: cada projeto usa
o roteador do seu framework, ou um componente próprio. Detectar a
CHAMADA, portanto, não é genérico.

O destino é. Toda aplicação declara no `registerApplication` as
rotas que possui, e isso vale para qualquer projeto single-spa.
Por isso a detecção é invertida: em vez de procurar chamadas de
navegação e descobrir para onde vão, procuramos expressões que
resolvem para uma rota de OUTRA aplicação. O que aciona a
navegação deixa de importar.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from tree_sitter import Node

from damfe.adapters.driven.reconstruction.ast import AstReader, ImportTable
from damfe.adapters.driven.reconstruction.singlespa.context import ScanContext
from damfe.adapters.driven.reconstruction.singlespa.expressions import (
    ExpressionEvaluator,
)
from damfe.adapters.driven.reconstruction.singlespa.ownership import Ownership
from damfe.adapters.driven.reconstruction.singlespa.reachability import placements
from damfe.domain import MicroFrontend, Navigation, SourceLocation



#: Elementos de roteador cujo `path`/`from` declara o caminho a que o
#: roteador responde, em vez de levar a ele.
ROUTE_ELEMENTS = frozenset({"Route", "Redirect"})

#: Contêineres cujos filhos diretos são rotas — no @reach/router, a
#: tela é filha de `<Router>` com `path` próprio.
ROUTE_CONTAINERS = frozenset({"Router", "Routes", "Switch"})


def _declares_route(attribute: Node, name: str) -> bool:
    """
    Se o atributo declara um caminho do roteador, em vez de navegar.

    Só no elemento de roteador: `path` num componente do projeto —
    `<Voltar path={routes.HOME}>` — é a URL para onde ele leva.
    """

    if name not in ("path", "from", "basename"):
        return False

    opening = attribute.parent

    tag = _tag(opening)

    if name == "basename":
        return bool(tag) and tag.endswith("Router")

    if tag in ROUTE_ELEMENTS:
        return True

    # Filho direto de um contêiner de rotas.
    element = opening if opening.type == "jsx_self_closing_element" else opening.parent

    parent = element.parent if element is not None else None

    if parent is not None and parent.type == "jsx_element":
        return _tag(parent.child_by_field_name("open_tag")) in ROUTE_CONTAINERS

    return False


def _tag(opening: Node | None) -> str | None:

    if opening is None:
        return None

    name = opening.child_by_field_name("name")

    return name.text.decode("utf-8", "replace") if name is not None else None

#: Módulos nativos do Node (`module.builtinModules`) que não existem no
#: navegador: o webpack 5 e o Vite não os embutem no pacote do cliente.
#: Ficam de fora os que têm pacote de mesmo nome para o navegador
#: (`events`, `buffer`, `util`, `url`, `process`, `assert`...), que o
#: código do cliente importa de verdade.
NODE_ONLY_MODULES = frozenset({
    "child_process", "cluster", "dgram", "diagnostics_channel", "dns", "dns/promises",
    "fs", "fs/promises", "http", "http2", "https", "inspector", "module", "net", "os",
    "path", "path/posix", "path/win32", "perf_hooks", "readline", "readline/promises",
    "repl", "tls", "trace_events", "tty", "v8", "vm", "wasi", "worker_threads",
})


def _callee(node: Node, source: bytes) -> str | None:

    function = node.child_by_field_name("function")

    return AstReader.text(function, source) if function is not None else None


def _runs_on_node(root: Node, source: bytes) -> bool:
    """
    Se o módulo roda no Node, e não no navegador: importa um módulo
    nativo que só existe lá (`import fs from "fs"`, `require("node:path")`).

    É o servidor que entrega o pacote, não o micro frontend: o
    `app.get("/")` do Express declara a rota que ele atende.
    """

    for node in AstReader.walk(root):

        if node.type == "import_statement":
            specifier = node.child_by_field_name("source")

        elif node.type == "call_expression" and _callee(node, source) == "require":
            arguments = node.child_by_field_name("arguments")
            specifier = arguments.named_children[0] if arguments is not None and arguments.named_children else None

        else:
            continue

        if specifier is None or specifier.type != "string":
            continue

        name = AstReader.strip_quotes(AstReader.text(specifier, source))

        if name.startswith("node:") or name in NODE_ONLY_MODULES:
            return True

    return False


#: Chamadas que recebem URL sem navegar.
NOT_NAVIGATION_CALLS = frozenset({"fetch"})

#: Métodos de `String` e `Array` cujo argumento é texto a comparar,
#: cortar ou juntar — nunca um destino.
TEXT_METHODS = frozenset({
    "startsWith", "endsWith", "includes", "indexOf", "lastIndexOf",
    "split", "join", "replace", "replaceAll", "concat", "match",
    "matchAll", "search", "padStart", "padEnd", "trim", "localeCompare",
})

#: Pacotes do React Router.
ROUTER_MODULES = frozenset({"react-router", "react-router-dom"})

#: Componentes cujo `to` é resolvido pelo roteador.
ROUTER_LINKS = frozenset({"Link", "NavLink", "Navigate"})

#: Roteadores que aceitam `basename`.
ROUTER_COMPONENTS = frozenset(
    {"BrowserRouter", "HashRouter", "MemoryRouter", "Router", "unstable_HistoryRouter"}
)

#: Fábricas de roteador de dados, com `basename` nas opções.
ROUTER_FACTORIES = frozenset({"createBrowserRouter", "createHashRouter", "createMemoryRouter"})

#: Funções que COMPARAM um padrão com a URL atual, sem ir a ela:
#: `useMatch`, `matchPath` e `matchRoutes` do React Router v6
#: (https://reactrouter.com/en/main/hooks/use-match), `useRouteMatch` do
#: v5, e `pathToActiveWhen` do single-spa
#: (https://single-spa.js.org/docs/api#pathtoactivewhen).
MATCHERS = {
    "react-router": frozenset({"useMatch", "matchPath", "matchRoutes", "useRouteMatch"}),
    "react-router-dom": frozenset({"useMatch", "matchPath", "matchRoutes", "useRouteMatch"}),
    "single-spa": frozenset({"pathToActiveWhen"}),
}

#: Ganchos que devolvem quem navega pelo roteador: a função do v6 e
#: o histórico do v5.
ROUTER_HOOKS = {"useNavigate": None, "useHistory": ("push", "replace")}


class NavigationExtractor:

    def __init__(
        self,
        context: ScanContext,
        microfrontends: list[MicroFrontend],
        requests: set[tuple[str, int]] | None = None,
    ):
        self.context = context

        self.microfrontends = microfrontends

        #: (arquivo, início) das chamadas que são requisição HTTP: o
        #: argumento delas é recurso a buscar, não destino, mesmo que o
        #: caminho coincida com a rota de outra aplicação.
        self.requests = requests or set()

        self.ownership = Ownership(context.repository, microfrontends)

        self.evaluator = ExpressionEvaluator(context.routes)

        #: unidade → `basename` do roteador dela
        self.basenames: dict[str, str] = {}

    def extract(self) -> list[Navigation]:

        found: list[Navigation] = []

        parsed = []

        for file_path in self.context.tree.source_files():

            try:
                root, source = self.context.reader.parse(file_path)
            except Exception:
                continue

            parsed.append((file_path, root, source))

        self.basenames = self._basenames(parsed)

        for file_path, root, source in parsed:
            found.extend(self._from_file(file_path, root, source))

        # De que tela parte cada navegação: a mesma pergunta da ponta
        # de um canal, feita uma vez para todas.
        if found:

            reached = placements(self.context, self.microfrontends)

            for item in found:
                item.on = reached.get(item.at.file, item.on)

        return sorted(
            found,
            key=lambda item: (
                item.source,
                item.target,
                item.at.file,
                item.at.line,
            ),
        )

    def _from_file(
        self,
        file_path: Path,
        root: Node,
        source: bytes,
    ) -> list[Navigation]:

        origin = self.ownership.of_file(file_path)

        # Código fora de qualquer unidade não navega de ninguém, e o
        # que roda no servidor não navega no navegador.
        if not origin or _runs_on_node(root, source):
            return []

        relative = self.context.relative(file_path)

        found: list[Navigation] = []

        routed = self._router_targets(root, source)

        matchers = self._matcher_names(root, source)

        for node in self._candidates(root):

            if self._is_request_argument(relative, node) or self._is_matcher_argument(node, source, matchers):
                continue

            value = self.evaluator.evaluate(node, source)

            # Base desconhecida pode ser outra origem — um CDN, uma
            # API —, e aí o caminho não é rota do sistema.
            if not value or value.based or not value.url.startswith("/"):
                continue

            url = value.url

            # `<Link to="/">` debaixo de `<BrowserRouter basename="/loja">`
            # vai para `/loja`: o React Router resolve o destino a partir
            # da base do roteador, não da raiz do site.
            if node.id in routed:
                url = self._under_basename(origin, url)

            target = self.ownership.of_route(url)

            if not target or target == origin:
                continue

            found.append(
                Navigation(
                    source=origin,
                    target=target,
                    expression=AstReader.text(node, source),
                    resolved_url=url,
                    match=value.match,
                    at=SourceLocation(
                        file=relative,
                        line=node.start_point.row + 1,
                        code=self._statement(node, source),
                    ),
                )
            )

        return found

    @staticmethod
    def _matcher_names(root: Node, source: bytes) -> set[str]:
        """Os nomes locais das funções de `MATCHERS` importadas no módulo."""

        return {
            record.local_name
            for record in ImportTable.records(root, source)
            if record.imported_name in MATCHERS.get(record.module, ())
        }

    @staticmethod
    def _is_matcher_argument(node: Node, source: bytes, matchers: set[str]) -> bool:

        arguments = node.parent

        if not matchers or arguments is None or arguments.type != "arguments" or arguments.parent is None:
            return False

        return _callee(arguments.parent, source) in matchers

    def _is_request_argument(self, relative: str, node: Node) -> bool:

        arguments = node.parent

        if arguments is None or arguments.type != "arguments" or arguments.parent is None:
            return False

        return (relative, arguments.parent.start_byte) in self.requests

    # ------------------------------------------------------------------
    # A base do roteador de cada unidade
    # ------------------------------------------------------------------

    def _basenames(self, parsed) -> dict[str, str]:
        """
        Unidade → `basename` do roteador que ela monta.

        Só quando há UM valor: a unidade com dois roteadores de bases
        diferentes deixa ambíguo de qual deles é cada link, e o
        destino fica como está escrito.
        """

        found: dict[str, set[str]] = {}

        for file_path, root, source in parsed:

            owner = self.ownership.of_file(file_path)

            if not owner:
                continue

            names = self._router_imports(root, source)

            if not names:
                continue

            for base in self._declared_basenames(root, source, names):
                found.setdefault(owner, set()).add(base)

        return {
            owner: next(iter(values))
            for owner, values in found.items()
            if len(values) == 1
        }

    def _declared_basenames(self, root: Node, source: bytes, names: dict[str, str]) -> Iterator[str]:

        for node in AstReader.walk(root):

            if node.type in ("jsx_opening_element", "jsx_self_closing_element"):

                if names.get(_tag(node) or "") not in ROUTER_COMPONENTS:
                    continue

                for attribute in node.named_children:

                    parts = attribute.named_children if attribute.type == "jsx_attribute" else []

                    if len(parts) < 2 or AstReader.text(parts[0], source) != "basename":
                        continue

                    value = parts[1]

                    if value.type == "jsx_expression" and value.named_children:
                        value = value.named_children[0]

                    resolved = self.evaluator.evaluate(value, source)

                    if resolved and resolved.match == "exact" and not resolved.based:
                        yield resolved.url

            elif node.type == "call_expression":

                function = node.child_by_field_name("function")

                if function is None or names.get(AstReader.text(function, source)) not in ROUTER_FACTORIES:
                    continue

                # `createBrowserRouter(rotas, { basename })`
                arguments = node.child_by_field_name("arguments")

                given = [child for child in arguments.named_children if child.type != "comment"] if arguments else []

                options = given[1] if len(given) > 1 and given[1].type == "object" else None

                for pair in options.named_children if options is not None else []:

                    key = pair.child_by_field_name("key") if pair.type == "pair" else None

                    if key is None or AstReader.strip_quotes(AstReader.text(key, source)) != "basename":
                        continue

                    resolved = self.evaluator.evaluate(pair.child_by_field_name("value"), source)

                    if resolved and resolved.match == "exact" and not resolved.based:
                        yield resolved.url

    @staticmethod
    def _router_imports(root: Node, source: bytes) -> dict[str, str]:
        """Nome local → nome exportado, para o que vem do React Router."""

        return {
            record.local_name: record.imported_name
            for record in ImportTable.records(root, source)
            if record.module in ROUTER_MODULES
        }

    def _router_targets(self, root: Node, source: bytes) -> set[int]:
        """
        Os nós de destino que o roteador resolve: o `to` dos links do
        React Router e o argumento de `navigate()` e `history.push()`.
        """

        names = self._router_imports(root, source)

        if not names:
            return set()

        found: set[int] = set()

        #: nome local → métodos que navegam (`None`: a própria função)
        navigators: dict[str, tuple[str, ...] | None] = {}

        for declarator in AstReader.find_all(root, "variable_declarator"):

            name = declarator.child_by_field_name("name")
            value = declarator.child_by_field_name("value")

            if name is None or value is None or name.type != "identifier" or value.type != "call_expression":
                continue

            hook = names.get(AstReader.text(value.child_by_field_name("function"), source))

            if hook in ROUTER_HOOKS:
                navigators[AstReader.text(name, source)] = ROUTER_HOOKS[hook]

        for node in AstReader.walk(root):

            if node.type == "jsx_attribute":

                parts = node.named_children

                if len(parts) < 2 or AstReader.text(parts[0], source) != "to":
                    continue

                if names.get(_tag(node.parent) or "") not in ROUTER_LINKS:
                    continue

                value = parts[1]

                found.add(value.id)
                found.update(child.id for child in value.named_children)

            elif node.type == "call_expression" and navigators:

                function = node.child_by_field_name("function")
                arguments = node.child_by_field_name("arguments")

                if function is None or arguments is None:
                    continue

                if function.type == "identifier":
                    name = AstReader.text(function, source)
                    navigates = name in navigators and navigators[name] is None

                elif function.type == "member_expression":
                    receiver = function.child_by_field_name("object")
                    method = function.child_by_field_name("property")
                    methods = navigators.get(AstReader.text(receiver, source)) if receiver is not None else None
                    navigates = bool(methods) and method is not None and AstReader.text(method, source) in methods

                else:
                    navigates = False

                if navigates:
                    found.update(child.id for child in arguments.named_children[:1])

        return found

    def _under_basename(self, owner: str, url: str) -> str:

        base = self.basenames.get(owner)

        if not base:
            return url

        base = "/" + base.strip("/")

        if base == "/":
            return url

        return base if url == "/" else base + url

    @staticmethod
    def _candidates(root: Node) -> Iterator[Node]:
        """
        As posições em que uma URL vira navegação.

        Argumento DIRETO de chamada cobre `navigate(rota)`; valor de
        atributo JSX cobre `<Link to={rota}>` e qualquer componente
        próprio que receba a rota por prop.

        Só o argumento direto, nunca aninhado: é o que mantém o
        `activeWhen: ["/users"]` do próprio `registerApplication`
        fora do resultado.

        Dois cortes. Atributo que DECLARA caminho em vez de levar a
        ele — `<Route path>`, `<Redirect from>`, `<Router basename>` —
        não é navegação: é o roteador dizendo o que responde ali. E
        `fetch(url)` busca dado, não leva o usuário a lugar nenhum.
        """

        for node in AstReader.walk(root):

            if node.type == "call_expression":

                function = node.child_by_field_name("function")

                if function is not None and function.type == "identifier" and (
                    function.text.decode("utf-8", "replace") in NOT_NAVIGATION_CALLS
                ):
                    continue

                # `url.endsWith("/")`, `path.split("/")`: método de
                # texto ou de lista recebe pedaço de texto, não destino.
                if function is not None and function.type == "member_expression":

                    method = function.child_by_field_name("property")

                    if method is not None and (
                        method.text.decode("utf-8", "replace") in TEXT_METHODS
                    ):
                        continue

                arguments = node.child_by_field_name("arguments")

                if not arguments:
                    continue

                for child in arguments.named_children:

                    if child.type != "comment":
                        yield child

            elif node.type == "jsx_attribute":

                parts = node.named_children

                if len(parts) < 2:
                    continue

                if _declares_route(node, parts[0].text.decode("utf-8", "replace")):
                    continue

                value = parts[1]

                if value.type != "jsx_expression":
                    yield value
                    continue

                for child in value.named_children:

                    if child.type != "comment":
                        yield child

    @staticmethod
    def _statement(node: Node, source: bytes) -> str:
        """O trecho de código em volta, para leitura humana."""

        current = node

        while current.parent and current.type not in {
            "expression_statement",
            "jsx_attribute",
            "jsx_self_closing_element",
            "return_statement",
        }:
            current = current.parent

        text = AstReader.text(current, source)

        return " ".join(text.split())[:160]
