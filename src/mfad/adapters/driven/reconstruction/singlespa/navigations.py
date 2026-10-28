"""
Navigation between applications.

There is no standard navigation API in single-spa: each project uses
its framework's router, or a component of its own. Detecting the
CALL, therefore, is not generic.

The target is. Every application declares in `registerApplication`
the routes it owns, and that holds for any single-spa project. That is
why detection is inverted: instead of looking for navigation calls and
finding out where they go, we look for expressions that resolve to a
route of ANOTHER application. What triggers the navigation no longer
matters.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from tree_sitter import Node

from mfad.adapters.driven.reconstruction.ast import AstReader, ImportTable
from mfad.adapters.driven.reconstruction.singlespa.context import ScanContext
from mfad.adapters.driven.reconstruction.singlespa.expressions import (
    ExpressionEvaluator,
)
from mfad.adapters.driven.reconstruction.singlespa.ownership import Ownership
from mfad.adapters.driven.reconstruction.singlespa.reachability import placements
from mfad.domain import MicroFrontend, Navigation, SourceLocation



#: Router elements whose `path`/`from` declares the path the router
#: answers to, instead of leading to it.
ROUTE_ELEMENTS = frozenset({"Route", "Redirect"})

#: Containers whose direct children are routes — in @reach/router, the
#: screen is a child of `<Router>` with its own `path`.
ROUTE_CONTAINERS = frozenset({"Router", "Routes", "Switch"})


def _declares_route(attribute: Node, name: str) -> bool:
    """
    Whether the attribute declares a router path, instead of navigating.

    Only on a router element: `path` on a project component —
    `<Voltar path={routes.HOME}>` — is the URL it leads to.
    """

    if name not in ("path", "from", "basename"):
        return False

    opening = attribute.parent

    tag = _tag(opening)

    if name == "basename":
        return bool(tag) and tag.endswith("Router")

    if tag in ROUTE_ELEMENTS:
        return True

    # Direct child of a routes container.
    element = opening if opening.type == "jsx_self_closing_element" else opening.parent

    parent = element.parent if element is not None else None

    if parent is not None and parent.type == "jsx_element":
        return _tag(parent.child_by_field_name("open_tag")) in ROUTE_CONTAINERS

    return False


def _has_literal_after(pattern: str, prefix: str) -> bool:
    """The pattern says more than the prefix and has some literal segment: `/{param}` alone is nobody's route."""

    segments = [segment for segment in pattern.split("?")[0].split("/") if segment]

    return any(segment != "{param}" for segment in segments) and len(pattern) > len(prefix)


def _tag(opening: Node | None) -> str | None:

    if opening is None:
        return None

    name = opening.child_by_field_name("name")

    return name.text.decode("utf-8", "replace") if name is not None else None

#: Node built-in modules (`module.builtinModules`) that do not exist in
#: the browser: webpack 5 and Vite do not bundle them into the client.
#: Left out are the ones that have a same-named package for the browser
#: (`events`, `buffer`, `util`, `url`, `process`, `assert`...), which
#: client code really imports.
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
    Whether the module runs on Node, not in the browser: it imports a
    built-in module that only exists there (`import fs from "fs"`,
    `require("node:path")`).

    It is the server that delivers the bundle, not the micro frontend:
    Express's `app.get("/")` declares the route it serves.
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


#: Calls that receive a URL without navigating.
NOT_NAVIGATION_CALLS = frozenset({"fetch"})

#: `String` and `Array` methods whose argument is text to compare, cut
#: or join — never a target.
TEXT_METHODS = frozenset({
    "startsWith", "endsWith", "includes", "indexOf", "lastIndexOf",
    "split", "join", "replace", "replaceAll", "concat", "match",
    "matchAll", "search", "padStart", "padEnd", "trim", "localeCompare",
})

#: React Router packages.
ROUTER_MODULES = frozenset({"react-router", "react-router-dom"})

#: Components whose `to` is resolved by the router.
ROUTER_LINKS = frozenset({"Link", "NavLink", "Navigate"})

#: Routers that accept `basename`.
ROUTER_COMPONENTS = frozenset(
    {"BrowserRouter", "HashRouter", "MemoryRouter", "Router", "unstable_HistoryRouter"}
)

#: Data router factories, with `basename` in the options.
ROUTER_FACTORIES = frozenset({"createBrowserRouter", "createHashRouter", "createMemoryRouter"})

#: Functions that COMPARE a pattern with the current URL, without going
#: to it: React Router v6's `useMatch`, `matchPath` and `matchRoutes`
#: (https://reactrouter.com/en/main/hooks/use-match), v5's
#: `useRouteMatch`, and single-spa's `pathToActiveWhen`
#: (https://single-spa.js.org/docs/api#pathtoactivewhen).
MATCHERS = {
    "react-router": frozenset({"useMatch", "matchPath", "matchRoutes", "useRouteMatch"}),
    "react-router-dom": frozenset({"useMatch", "matchPath", "matchRoutes", "useRouteMatch"}),
    "single-spa": frozenset({"pathToActiveWhen"}),
}

#: Hooks that return what navigates through the router: v6's function
#: and v5's history.
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

        #: (file, start) of the calls that are HTTP requests: their
        #: argument is a resource to fetch, not a target, even if the
        #: path matches another application's route.
        self.requests = requests or set()

        self.ownership = Ownership(context.repository, microfrontends)

        self.evaluator = ExpressionEvaluator(context.routes)

        #: unit → its router's `basename`
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

        # Which screen each navigation starts from: the same question as
        # for a channel end, asked once for all of them.
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

        # Code outside any unit navigates from nobody, and what runs on
        # the server does not navigate in the browser.
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

            # An unknown base may be another origin — a CDN, an API —,
            # and then the path is not a route of the system.
            if not value or value.based or not value.url.startswith("/"):
                continue

            url = value.url

            # `/movie/${id}`: with the rest of the path, the target
            # matches the dynamic route `/movie/:id`, which the prefix
            # `/movie/` does not reach. With no text after the prefix,
            # the prefix stays.
            if value.pattern and _has_literal_after(value.pattern, url):
                url = value.pattern

            # `<Link to="/">` under `<BrowserRouter basename="/loja">`
            # goes to `/loja`: React Router resolves the target from the
            # router's base, not from the site root.
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
        """The local names of the `MATCHERS` functions imported in the module."""

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
    # The router base of each unit
    # ------------------------------------------------------------------

    def _basenames(self, parsed) -> dict[str, str]:
        """
        Unit → `basename` of the router it mounts.

        Only when there is ONE value: a unit with two routers with
        different bases makes it ambiguous which one each link belongs
        to, and the target stays as written.
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

                # `createBrowserRouter(routes, { basename })`
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
        """Local name → exported name, for what comes from React Router."""

        return {
            record.local_name: record.imported_name
            for record in ImportTable.records(root, source)
            if record.module in ROUTER_MODULES
        }

    def _router_targets(self, root: Node, source: bytes) -> set[int]:
        """
        The target nodes the router resolves: the `to` of React Router
        links and the argument of `navigate()` and `history.push()`.
        """

        names = self._router_imports(root, source)

        if not names:
            return set()

        found: set[int] = set()

        #: local name → methods that navigate (`None`: the function itself)
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
        The positions in which a URL becomes navigation.

        A DIRECT call argument covers `navigate(rota)`; a JSX attribute
        value covers `<Link to={rota}>` and any custom component that
        receives the route through a prop.

        Only the direct argument, never nested: that is what keeps the
        `activeWhen: ["/users"]` of `registerApplication` itself out of
        the result.

        Two cuts. An attribute that DECLARES a path instead of leading
        to it — `<Route path>`, `<Redirect from>`, `<Router basename>` —
        is not navigation: it is the router saying what answers there.
        And `fetch(url)` fetches data, it does not take the user
        anywhere.
        """

        for node in AstReader.walk(root):

            if node.type == "call_expression":

                function = node.child_by_field_name("function")

                if function is not None and function.type == "identifier" and (
                    function.text.decode("utf-8", "replace") in NOT_NAVIGATION_CALLS
                ):
                    continue

                # `url.endsWith("/")`, `path.split("/")`: a text or list
                # method receives a piece of text, not a target.
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
        """The surrounding code snippet, for human reading."""

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
