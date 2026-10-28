"""
Calls to external services.

Detection depends neither on the micro frontend framework nor on how
the project is organized. It starts from generic anchors — the web
platform API, the import specifier of the client libraries and the
injected type of Angular's `HttpClient` — and resolves the path with
partial evaluation of the expression.

Projects often wrap the HTTP client in a function of their own:

    export function fetchApi(url, options) {
      return fetch(`${API_BASE_URL}${url}`, options);
    }

and the URL only appears in whoever calls `fetchApi("/contas")`. So a
function that FORWARDS one of its parameters as the URL of a client
becomes a client too, with the URL at that position — and this
propagates: a service that calls `fetchApi(endpoint)` with its own
parameter is a client in the same way. The criterion is data flow, not
name: the function does not need to be called `get` nor live in
`services/`.

A call inside an unused function does not count, by the same dead-code
criterion used for communication.

Knowing which SCREEN makes the call requires following the imports: the
call lives in the service module, not in the screen that uses it.
Cross-file reachability solves this.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Node

from mfad.adapters.driven.reconstruction.ast import AstReader, ImportTable, ModuleResolver
from mfad.adapters.driven.reconstruction.ast.resolver import canonical
from mfad.adapters.driven.reconstruction.ast.symbols import (
    ModuleSymbols,
    SymbolIndex,
    declared_value,
    parameters,
    returned_expression,
    unwrap,
)
from mfad.adapters.driven.reconstruction.singlespa import http_clients
from mfad.adapters.driven.reconstruction.singlespa.context import ScanContext
from mfad.adapters.driven.reconstruction.singlespa.expressions import (
    PREFIX,
    ExpressionEvaluator,
)
from mfad.adapters.driven.reconstruction.singlespa.forwarding import (
    Parameter,
    parameter_of,
    until_stable,
)
from mfad.adapters.driven.reconstruction.singlespa import shared
from mfad.adapters.driven.reconstruction.singlespa.liveness import Liveness
from mfad.adapters.driven.reconstruction.singlespa.ownership import Ownership
from mfad.adapters.driven.reconstruction.singlespa.reachability import (
    Reachability,
)
from mfad.domain import ApiCall, MicroFrontend, SourceLocation


#: URL segment that depends on a runtime value: `/users/{param}`.
PARAM = "{param}"

#: A URL whose segment is `{param}` gets this match.
PATTERN = "pattern"

#: How many indirections — variable, function that returns the URL —
#: are followed from an argument.
MAX_DEPTH = 4


#: URL piece: known text, parameter, or `None` for a value that does
#: not resolve.
Part = str | Parameter | None


@dataclass(frozen=True)
class Shape:
    """Where an HTTP call takes its URL and verb from."""

    url: Node
    client: str

    #: fixed verb of the call (`api.post`)
    method: str | None = None

    #: argument the `method` comes from (`fetch(url, { method })`)
    options: Node | None = None

    #: text the wrapping function puts before the received URL
    prefix: str = ""

    #: and after it, with `{param}` in the runtime segment
    suffix: str = ""

    #: there is an unknown base before everything
    based: bool = False


@dataclass(frozen=True)
class Wrapper:
    """Project function that is an HTTP client because it forwards the URL."""

    client: str
    url: int
    prefix: str = ""
    suffix: str = ""
    based: bool = False
    method: str | None = None

    #: parameter the `method` comes from, when it is forwarded
    method_from: int | None = None


def extracted(context: ScanContext, microfrontends: list[MicroFrontend]) -> tuple[list[ApiCall], set[tuple[str, int]]]:
    """
    The HTTP calls and where each request is, memoized in the context:
    navigation needs the requests, and extraction is expensive.
    """

    key = tuple(item.id for item in microfrontends)

    if key not in context._api:
        extractor = ApiCallExtractor(context, microfrontends)
        calls = extractor.extract()
        context._api[key] = (calls, extractor.requests)

    return context._api[key]


class ApiCallExtractor:

    def __init__(
        self,
        context: ScanContext,
        microfrontends: list[MicroFrontend],
    ):
        self.context = context

        self.ownership = Ownership(context.repository, microfrontends)

        #: shared package file → the units that import it
        self.shared = shared.importers(context, microfrontends)

        self.evaluator = ExpressionEvaluator(context.routes)

        self.index: SymbolIndex = context.symbols()

        self.liveness = Liveness(context)

        self._bindings_cache: dict[Path, dict[str, str]] = {}

        self.wrappers: dict[tuple[Path, str], Wrapper] = {}

        #: the last name of each wrapper, so that only a call that may
        #: be one of them gets resolved
        self._wrapper_names: set[str] = set()

        self.callers = self._callers(microfrontends)

        #: (file, start) of every call that is an HTTP request, live or
        #: not, with a resolved path or not: the URL it receives is a
        #: resource to fetch, never a navigation target.
        self.requests: set[tuple[str, int]] = set()

    def extract(self) -> list[ApiCall]:

        files = [
            symbols
            for file_path in self.context.tree.source_files()
            if (symbols := self.index.of(file_path)) is not None
        ]

        self._find_wrappers(files)

        found: list[ApiCall] = []

        for symbols in files:
            found.extend(self._from_file(symbols))

        return sorted(
            found,
            key=lambda item: (
                item.microfrontend,
                item.path,
                item.method,
                item.at.file,
                item.at.line,
            ),
        )

    def _callers(
        self,
        microfrontends: list[MicroFrontend],
    ) -> dict[Path, tuple[list[str], list[str]]]:
        """
        File -> (screens, fragments) that reach it.

        Inverted on purpose: extraction finds the call and needs to ask
        who reaches it, not the other way round.
        """

        reachability = Reachability(self.context)

        screens: dict[Path, list[str]] = {}
        fragments: dict[Path, list[str]] = {}

        origins = [
            (screen.file, screen.component, screens)
            for microfrontend in microfrontends
            for screen in microfrontend.screens
        ] + [
            (fragment.file, fragment.name, fragments)
            for microfrontend in microfrontends
            for fragment in microfrontend.fragments
        ]

        for relative, name, target in origins:

            if not relative:
                continue

            origin = self.context.repository / relative

            if not origin.is_file():
                continue

            for reached in reachability.reachable_from(origin):
                target.setdefault(canonical(reached), []).append(name)

        return {
            path: (
                sorted(set(screens.get(path, []))),
                sorted(set(fragments.get(path, []))),
            )
            for path in set(screens) | set(fragments)
        }

    def _from_file(self, symbols: ModuleSymbols) -> list[ApiCall]:

        owner = self.ownership.of_file(symbols.path)

        # A call outside any unit only happens inside whoever imports
        # the package it lives in (`shared`); with no one, it belongs to
        # no micro frontend.
        owners = [owner] if owner else sorted(self.shared.get(canonical(symbols.path), ()))

        if not owners:
            return []

        relative = self.context.relative(symbols.path)

        screens, fragments = self.callers.get(symbols.path, ([], []))

        found: list[ApiCall] = []

        for node in AstReader.find_all(symbols.root, "call_expression"):

            shape = self._shape(node, symbols)

            if shape is None:
                continue

            self.requests.add((relative, node.start_byte))

            path = self._path(shape, symbols)

            # A call in a function nobody calls does not happen — the
            # same criterion as communication and global state.
            if path is None or not self.liveness.is_live(node, symbols):
                continue

            url, match = path

            found.extend(
                ApiCall(
                    microfrontend=owner,
                    method=self._method(shape, symbols),
                    path=url,
                    match=match,
                    client=shape.client,
                    at=SourceLocation(
                        file=relative,
                        line=node.start_point.row + 1,
                        code=self._line(node, symbols.source),
                    ),
                    screens=screens,
                    fragments=fragments,
                )
                for owner in owners
            )

        return found

    # ------------------------------------------------------------------
    # Functions that wrap a client
    # ------------------------------------------------------------------

    def _find_wrappers(self, files: list[ModuleSymbols]) -> None:
        """
        The functions that forward a parameter as the URL, in layers.

        The first layer wraps a known client; each following layer
        wraps one from the previous layer.
        """

        def step(node: Node, symbols: ModuleSymbols) -> bool:

            shape = self._shape(node, symbols)

            wrapper = self._as_wrapper(shape, symbols) if shape is not None else None

            if wrapper is None or wrapper[0] in self.wrappers:
                return False

            key, item = wrapper

            self.wrappers[key] = item
            self._wrapper_names.add(key[1].rpartition(".")[2])

            return True

        until_stable(files, step)

    def _as_wrapper(
        self,
        shape: Shape,
        symbols: ModuleSymbols,
    ) -> tuple[tuple[Path, str], Wrapper] | None:
        """
        The enclosing function, if it forwards a parameter as the URL.

        The URL must start with the parameter, with at most one unknown
        base and text before it: `${base}${url}`, `base + url`, `url`.
        More path may follow it, as in `${base}${endpoint}/${id}`: the
        text stays, and what is runtime becomes `{param}`. If the text
        before it is already a service path — `/api/` — the call is
        recorded where it is, as it always was, and the function does
        not become a wrapper: there is no way to know what the
        parameter completes.
        """

        if self._path(shape, symbols) is not None:
            return None

        parts = self._full_parts(shape, symbols)

        chosen = next(
            (index for index, part in enumerate(parts) if isinstance(part, Parameter) and self._url_at(parts, index)),
            None,
        )

        if chosen is None:
            return None

        tail = parts[chosen]

        suffix = "".join(part if isinstance(part, str) else PARAM for part in parts[chosen + 1 :])

        parts = parts[: chosen + 1]

        # The parameter must belong to the function enclosing the call,
        # not to a function that merely returned the URL to it.
        if not self._encloses(tail.function, shape.url):
            return None

        head = parts[:-1]

        based = False

        while head and not isinstance(head[0], str):
            head = head[1:]
            based = True

        if any(not isinstance(part, str) for part in head):
            return None

        key = self.index.key_of(tail.function, symbols)

        if key is None:
            return None

        method, method_from = shape.method, None

        if method is None and shape.options is not None:
            method, method_from = self._forwarded_method(shape.options, tail.function, symbols)

        return (symbols.path, key), Wrapper(
            client=shape.client,
            url=tail.index,
            prefix="".join(head),
            suffix=suffix + shape.suffix,
            based=based,
            method=method,
            method_from=method_from,
        )

    @staticmethod
    def _url_at(parts: list[Part], index: int) -> bool:
        """
        Whether the parameter at the position can be the URL: before it,
        only an unknown base followed by text; after it, nothing or the
        continuation of the path (`/`, `?`).
        """

        head = parts[:index]

        while head and not isinstance(head[0], str):
            head = head[1:]

        if any(not isinstance(part, str) for part in head):
            return False

        rest = parts[index + 1 :]

        return not rest or (isinstance(rest[0], str) and rest[0][:1] in ("/", "?"))

    def _forwarded_method(
        self,
        options: Node,
        function: Node,
        symbols: ModuleSymbols,
    ) -> tuple[str | None, int | None]:
        """The fixed verb, or the options parameter it comes from."""

        options = unwrap(options)

        names = parameters(function, symbols.source)

        if options.type == "identifier" and symbols.text(options) in names:
            return None, names.index(symbols.text(options))

        if options.type != "object":
            return None, None

        method = self._option(options, "method", symbols.source)

        if method:
            return method.upper(), None

        # `{ ...options, headers }`: the `method` comes from the caller.
        for child in options.named_children:

            if child.type != "spread_element":
                continue

            spread = [item for item in child.named_children if item.type == "identifier"]

            if spread and symbols.text(spread[0]) in names:
                return None, names.index(symbols.text(spread[0]))

        return None, None

    # ------------------------------------------------------------------
    # The shape of each call
    # ------------------------------------------------------------------

    def _shape(self, node: Node, symbols: ModuleSymbols) -> Shape | None:

        return (
            self._platform_call(node, symbols)
            or self._client_call(node, symbols)
            or self._wrapper_call(node, symbols)
        )

    def _platform_call(self, node: Node, symbols: ModuleSymbols) -> Shape | None:
        """`fetch(url, { method })` and `xhr.open(method, url)`."""

        function = node.child_by_field_name("function")

        if not function:
            return None

        text = symbols.text(function)

        arguments = self._arguments(node)

        if text == http_clients.PLATFORM or text.endswith(f".{http_clients.PLATFORM}"):

            if not arguments:
                return None

            return Shape(
                url=arguments[0],
                client="fetch",
                options=arguments[1] if len(arguments) > 1 else None,
            )

        if function.type != "member_expression":
            return None

        receiver = function.child_by_field_name("object")
        name = function.child_by_field_name("property")

        if not receiver or not name or symbols.text(name) != "open":
            return None

        if self._bindings(symbols).get(symbols.text(receiver)) != http_clients.XHR_CONSTRUCTOR:
            return None

        if len(arguments) < 2:
            return None

        method = self.evaluator.evaluate(arguments[0], symbols.source)

        return Shape(
            url=arguments[1],
            client="xmlhttprequest",
            method=(method.url if method else "?").upper(),
        )

    def _client_call(self, node: Node, symbols: ModuleSymbols) -> Shape | None:
        """`api.get(url)`, `this.http.get(url)` and `axios({ url, method })`."""

        function = node.child_by_field_name("function")

        if not function:
            return None

        arguments = self._arguments(node)

        if not arguments:
            return None

        by_module = {item.module: item for item in http_clients.CLIENTS}

        bindings = self._bindings(symbols)

        if function.type == "member_expression":

            receiver = function.child_by_field_name("object")
            name = function.child_by_field_name("property")

            if not receiver or not name:
                return None

            module = bindings.get(symbols.text(receiver))

            client = by_module.get(module or "")

            if not client:
                return None

            verb = symbols.text(name)

            if verb not in client.methods:
                return None

            if verb in client.verb_first:

                if len(arguments) < 2:
                    return None

                method = self.evaluator.evaluate(arguments[0], symbols.source)

                return Shape(
                    url=arguments[1],
                    client=module,
                    method=(method.url if method else "?").upper(),
                )

            if verb == "request":
                return Shape(
                    url=arguments[0],
                    client=module,
                    options=arguments[1] if len(arguments) > 1 else None,
                )

            if verb == "jsonp":
                return Shape(url=arguments[0], client=module, method="GET")

            return Shape(url=arguments[0], client=module, method=verb.upper())

        # direct call on the library itself: `axios({ url })`
        if function.type == "identifier":

            module = bindings.get(symbols.text(function))

            client = by_module.get(module or "")

            if not client or not client.callable_directly:
                return None

            config = unwrap(arguments[0])

            if config.type == "object":

                url = self._option_node(config, "url", symbols.source)

                return Shape(url=url, client=module, options=config) if url else None

            return Shape(
                url=arguments[0],
                client=module,
                options=arguments[1] if len(arguments) > 1 else None,
            )

        return None

    def _wrapper_call(self, node: Node, symbols: ModuleSymbols) -> Shape | None:
        """Call to a project function that wraps a client."""

        function = unwrap(node.child_by_field_name("function"))

        if function is None:
            return None

        name = function.child_by_field_name("property") if function.type == "member_expression" else function

        if name is None or symbols.text(name) not in self._wrapper_names:
            return None

        target = self.index.callee(node, symbols)

        wrapper = self.wrappers.get(target) if target else None

        if wrapper is None:
            return None

        arguments = self._arguments(node)

        if wrapper.url >= len(arguments):
            return None

        options = (
            arguments[wrapper.method_from]
            if wrapper.method_from is not None and wrapper.method_from < len(arguments)
            else None
        )

        return Shape(
            url=arguments[wrapper.url],
            client=wrapper.client,
            method=wrapper.method,
            options=options,
            prefix=wrapper.prefix,
            suffix=wrapper.suffix,
            based=wrapper.based,
        )

    # ------------------------------------------------------------------
    # Who is an HTTP client in this file
    # ------------------------------------------------------------------

    def _bindings(self, symbols: ModuleSymbols) -> dict[str, str]:
        """
        Local names that behave as an HTTP client.

        Starts from the imports of the known libraries and propagates
        to the instances created from them — that is the case of
        `const api = axios.create({ baseURL })`, where the call never
        happens on the imported name. An instance created in one
        project module and imported by another also counts.

        In Angular the client is whatever was injected by the
        `HttpClient` type: `this.http`, when the `http` field has that
        type.
        """

        if symbols.path in self._bindings_cache:
            return self._bindings_cache[symbols.path]

        # Import cycle: the file still being computed does not contribute.
        self._bindings_cache[symbols.path] = {}

        by_module = {client.module: client for client in http_clients.CLIENTS}

        bindings: dict[str, str] = {}

        #: local name of the injectable type → module
        injectable: dict[str, str] = {}

        for record in ImportTable.records(symbols.root, symbols.source):

            client = by_module.get(record.module)

            if client and client.injected:

                if record.imported_name == client.injected:
                    injectable[record.local_name] = client.module

            elif client:
                bindings[record.local_name] = client.module

            else:

                # Instance created in another project module.
                target = ModuleResolver.resolve(record.module, symbols.path)

                other = self.index.of(target) if target else None

                if other is not None:

                    exported = other.exports.get(record.imported_name, record.imported_name)

                    origin = self._bindings(other).get(exported)

                    if origin:
                        bindings[record.local_name] = origin

        # `new XMLHttpRequest()`, `axios.create()`, `inject(HttpClient)`
        for node in AstReader.find_all(symbols.root, "variable_declarator"):

            name_node = node.child_by_field_name("name")
            value_node = node.child_by_field_name("value")

            if not name_node or not value_node or name_node.type != "identifier":
                continue

            origin = self._origin(unwrap(value_node), symbols.source, bindings, by_module, injectable)

            if origin:
                bindings[symbols.text(name_node)] = origin

        for fields in symbols.fields.values():

            for field_name, kind in fields.items():

                if kind in injectable:
                    bindings[f"this.{field_name}"] = injectable[kind]

        self._bindings_cache[symbols.path] = bindings

        return bindings

    @staticmethod
    def _origin(
        value: Node,
        source: bytes,
        bindings: dict[str, str],
        by_module: dict,
        injectable: dict[str, str],
    ) -> str | None:

        text = AstReader.text(value, source).strip()

        if value.type == "new_expression":

            if http_clients.XHR_CONSTRUCTOR in text:
                return http_clients.XHR_CONSTRUCTOR

            return None

        # direct alias: `const client = axios`
        if value.type == "identifier" and text in bindings:
            return bindings[text]

        if value.type != "call_expression":
            return None

        function = value.child_by_field_name("function")

        if not function:
            return None

        # `const http = inject(HttpClient)`
        if function.type == "identifier" and AstReader.text(function, source) == "inject":

            arguments = value.child_by_field_name("arguments")

            named = [item for item in arguments.named_children if item.type == "identifier"] if arguments else []

            return injectable.get(AstReader.text(named[0], source)) if named else None

        if function.type != "member_expression":
            return None

        receiver = function.child_by_field_name("object")
        method = function.child_by_field_name("property")

        if not receiver or not method:
            return None

        module = bindings.get(AstReader.text(receiver, source))

        if not module:
            return None

        client = by_module.get(module)

        if not client:
            return None

        return (
            module
            if AstReader.text(method, source) in client.factories
            else None
        )

    # ------------------------------------------------------------------
    # The URL
    # ------------------------------------------------------------------

    def _full_parts(self, shape: Shape, symbols: ModuleSymbols) -> list[Part]:
        """The URL pieces, with what the wrapper puts before them."""

        parts = self._parts(shape.url, symbols, 0)

        head: list[Part] = [None] if shape.based else []

        if shape.prefix:
            head.append(shape.prefix)

        # Wrapper of the `${base}${endpoint}` kind: the caller passes
        # the path relative to the base — `"parametro"` —, and the slash
        # separating them is in the base.
        elif shape.based and parts and isinstance(parts[0], str) and not (
            parts[0].startswith("/") or parts[0].startswith("http")
        ):
            parts = ["/" + parts[0], *parts[1:]]

        return head + parts + ([shape.suffix] if shape.suffix else [])

    def _path(self, shape: Shape, symbols: ModuleSymbols) -> tuple[str, str] | None:
        """The service path and the match, if it is an endpoint."""

        parts = self._full_parts(shape, symbols)

        # The unknown base at the start is left out: a service's path
        # does not depend on it.
        based = False

        while parts and not isinstance(parts[0], str):
            parts = parts[1:]
            based = True

        if not parts:
            return None

        text = "".join(part if isinstance(part, str) else PARAM for part in parts)

        # `${base}.json`, `${nome}-x`: what follows the base is not a path.
        if based and not text.startswith("/"):
            return None

        # The query and the fragment are not part of the route's
        # identity: `/gigs?page=2` and `/gigs` are the same contract.
        path = text.split("?")[0].split("#")[0]

        # Repeated slashes and a trailing slash do not change the
        # resource: `/tercero/` and `/tercero` are the same contract.
        path = re.sub(r"(?<!:)/{2,}", "/", path)

        if len(path) > 1:
            path = path.rstrip("/") or "/"

        if not self._is_endpoint(path):
            return None

        return path, (PATTERN if PARAM in path else "exact")

    def _parts(self, node: Node | None, symbols: ModuleSymbols, depth: int) -> list[Part]:

        node = unwrap(node)

        if node is None or depth > MAX_DEPTH:
            return [None]

        if node.type == "string":
            return [AstReader.strip_quotes(symbols.text(node))]

        if node.type == "template_string":
            return self._template_parts(node, symbols, depth)

        if node.type == "binary_expression":

            operator = node.child_by_field_name("operator")

            if operator is None or symbols.text(operator) != "+":
                return [None]

            return (
                self._parts(node.child_by_field_name("left"), symbols, depth)
                + self._parts(node.child_by_field_name("right"), symbols, depth)
            )

        if node.type == "identifier":

            parameter = parameter_of(node, symbols)

            if parameter is not None:
                return [parameter]

            value = declared_value(node, symbols.source)

            if value is not None:
                return self._parts(value, symbols, depth + 1)

        # `cond ? `${base}${url}/${id}` : `${base}${url}``: what counts is
        # what the two forms have in common, if it is the received URL.
        if node.type == "ternary_expression":

            consequence = self._parts(node.child_by_field_name("consequence"), symbols, depth)
            alternative = self._parts(node.child_by_field_name("alternative"), symbols, depth)

            if consequence == alternative:
                return consequence

            common: list[Part] = []

            for left, right in zip(consequence, alternative):
                if left != right:
                    break
                common.append(left)

            return common if common and isinstance(common[-1], Parameter) else [None]

        # `new URL(caminho, base)` (https://url.spec.whatwg.org/#constructors).
        if node.type == "new_expression":

            constructor = node.child_by_field_name("constructor")

            arguments = self._arguments(node)

            if constructor is not None and symbols.text(constructor) == "URL" and arguments:

                path = self._parts(arguments[0], symbols, depth)

                if len(arguments) == 1 or (isinstance(path[0], str) and path[0].startswith("http")):
                    return path

                # An absolute path replaces the base's path and keeps only the origin.
                if isinstance(path[0], str) and path[0].startswith("/"):
                    return [None, *path]

                return self._parts(arguments[1], symbols, depth) + path

        # `url.toString()` and `url.href` of a `URL`.
        if node.type == "call_expression":

            function = unwrap(node.child_by_field_name("function"))

            if (
                function is not None
                and function.type == "member_expression"
                and symbols.text(function.child_by_field_name("property")) == "toString"
                and not self._arguments(node)
                and self._is_url_object(function.child_by_field_name("object"), symbols)
            ):
                return self._parts(function.child_by_field_name("object"), symbols, depth)

        if node.type == "member_expression" and symbols.text(node.child_by_field_name("property")) == "href":

            if self._is_url_object(node.child_by_field_name("object"), symbols):
                return self._parts(node.child_by_field_name("object"), symbols, depth)

        # `buildUrl(id)`: a project function that only returns the URL.
        if node.type == "call_expression":

            target = self.index.callee(node, symbols)

            function = self.index.function(*target) if target else None

            returned = returned_expression(function.node) if function else None

            if returned is not None:
                owner = self.index.of(target[0])
                return self._parts(returned, owner, depth + 1) if owner else [None]

        # Repository constant and `rota.replace(":id", id)`.
        value = self.evaluator.evaluate(node, symbols.source)

        if value is None:
            return [None]

        return (
            ([None] if value.based else [])
            + [value.url]
            + ([None] if value.match == PREFIX else [])
        )

    def _template_parts(self, node: Node, symbols: ModuleSymbols, depth: int) -> list[Part]:

        parts: list[Part] = []

        position = node.start_byte + 1

        for child in node.named_children:

            if child.type != "template_substitution":
                continue

            if child.start_byte > position:
                parts.append(symbols.source[position:child.start_byte].decode("utf-8", "replace"))

            inner = [item for item in child.named_children if item.type != "comment"]

            parts.extend(self._parts(inner[0], symbols, depth) if inner else [None])

            position = child.end_byte

        if node.end_byte - 1 > position:
            parts.append(symbols.source[position:node.end_byte - 1].decode("utf-8", "replace"))

        return parts

    @staticmethod
    def _is_url_object(node: Node | None, symbols: ModuleSymbols) -> bool:
        """`new URL(...)`, directly or through the variable holding it."""

        node = unwrap(node)

        if node is not None and node.type == "identifier":
            node = unwrap(declared_value(node, symbols.source))

        if node is None or node.type != "new_expression":
            return False

        constructor = node.child_by_field_name("constructor")

        return constructor is not None and symbols.text(constructor) == "URL"

    @staticmethod
    def _encloses(function: Node, node: Node) -> bool:

        current = node.parent

        while current is not None:

            if current.id == function.id:
                return True

            current = current.parent

        return False

    # ------------------------------------------------------------------

    def _method(self, shape: Shape, symbols: ModuleSymbols) -> str:

        if shape.method:
            return shape.method

        options = unwrap(shape.options) if shape.options is not None else None

        if options is not None:

            method = self._option(options, "method", symbols.source)

            if method:
                return method.upper()

        return "GET"

    @staticmethod
    def _arguments(node: Node) -> list[Node]:

        arguments = node.child_by_field_name("arguments")

        if not arguments:
            return []

        return [
            child
            for child in arguments.named_children
            if child.type != "comment"
        ]

    @staticmethod
    def _option_node(node: Node, key: str, source: bytes) -> Node | None:

        if node.type != "object":
            return None

        for pair in node.named_children:

            if pair.type != "pair":
                continue

            key_node = pair.child_by_field_name("key")
            value_node = pair.child_by_field_name("value")

            if key_node and value_node and AstReader.strip_quotes(AstReader.text(key_node, source)) == key:
                return value_node

        return None

    def _option(self, node: Node, key: str, source: bytes) -> str | None:

        value_node = self._option_node(node, key, source)

        if value_node is None:
            return None

        value = self.evaluator.evaluate(value_node, source)

        return value.url if value else None

    @staticmethod
    def _is_endpoint(value: str) -> bool:
        """
        Discards what is clearly not a service address.

        A relative module path and an empty string come in through the
        same paths as a URL; the filter keeps them from becoming API
        calls.
        """

        if value.startswith("http"):

            # A fully literal absolute URL names the service by its address.
            if PARAM not in value:
                return True

            # With a runtime segment, what names it is the path after the
            # host: `http://localhost:${porta}${url}` is a proxy, not a
            # service.
            _, _, rest = value.partition("://")
            _, slash, path = rest.partition("/")
            value = slash + path

        if not value.startswith("/"):
            return False

        # With no literal segment at all — `/`, `/{param}` — the path
        # names no service, and would merge unrelated calls into a
        # single route in `hammering-apis`.
        return any(
            segment.replace(PARAM, "")
            for segment in value.split("/")
        )

    @staticmethod
    def _line(node: Node, source: bytes) -> str:

        return " ".join(AstReader.text(node, source).split())[:160]
