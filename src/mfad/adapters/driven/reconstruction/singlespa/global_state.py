"""
Access to global state.

Two micro frontends that read the same slice of state are coupled
without exchanging messages and without importing anything from each
other — a coupling none of the other extractions sees.

Detection is by known library, identified by the import specifier.
There is no naming heuristic: what comes from `react-redux` is state
access, whatever the variable is called.

For the libraries, only READS are extracted.
`useSelector((state) => state.cart)` walks the path explicitly, and
that is what gets recorded. A write — `dispatch(addProduto(item))` —
reveals only the action's name at the call site; knowing which slice it
changes would require following the reducer, which may not even be in
the same repository.

Browser storage — `localStorage` and `sessionStorage` — is also global
state, and one of the most common between micro frontends: the
authentication token written by one and read by all. Here both reads
and writes are included, because both state the key.

A Redux store created inside the unit itself is not global: it is that
unit's state. Only what is read from a store that may be shared counts
— created outside, by the orchestrator or by a common package.

A project function that forwards one of its parameters as a storage key
— `setLocalStorageItem(key, value)` — becomes a storage access too, and
the key is read at its callers. The access belongs to the caller: the
utility may live in a common package, and it is each micro frontend
that uses it that touches that key.

An access inside a function nobody calls does not count, by the same
dead-code criterion used for communication.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Node

from mfad.adapters.driven.reconstruction.ast import AstReader, ImportTable
from mfad.adapters.driven.reconstruction.ast.symbols import (
    ModuleSymbols,
    SymbolIndex,
    unwrap,
)
from mfad.adapters.driven.reconstruction.singlespa import libraries
from mfad.adapters.driven.reconstruction.singlespa.context import ScanContext
from mfad.adapters.driven.reconstruction.singlespa.expressions import (
    EXACT,
    ExpressionEvaluator,
)
from mfad.adapters.driven.reconstruction.singlespa.forwarding import (
    Parameter,
    parameter_of,
    until_stable,
)
from mfad.adapters.driven.reconstruction.ast.resolver import canonical
from mfad.adapters.driven.reconstruction.singlespa import shared
from mfad.adapters.driven.reconstruction.singlespa.liveness import Liveness
from mfad.adapters.driven.reconstruction.singlespa.ownership import Ownership
from mfad.domain import MicroFrontend, SourceLocation, StateAccess


#: Key piece: known text, parameter, or `None` for a value that does
#: not resolve.
Part = str | Parameter | None

#: Key segment that depends on a runtime value, as in URLs.
PARAM = "{param}"


@dataclass(frozen=True)
class Forward:
    """An access the function makes with the key it receives."""

    #: `localStorage` or `sessionStorage`
    kind: str

    #: position of the parameter that is the key
    index: int

    #: text the function puts before and after the received key
    prefix: str
    suffix: str

    access: str


@dataclass(frozen=True)
class Target:
    """A call that accesses storage, and where the key comes from."""

    kind: str
    access: str

    #: `None` in `clear()`, which writes to every key
    key: Node | None
    prefix: str = ""
    suffix: str = ""


class GlobalStateExtractor:

    def __init__(
        self,
        context: ScanContext,
        microfrontends: list[MicroFrontend],
    ):
        self.context = context

        self.ownership = Ownership(context.repository, microfrontends)

        #: shared package file → the units that import it
        self.shared = shared.importers(context, microfrontends)

        self.known = {item.id for item in microfrontends}

        self.evaluator = ExpressionEvaluator(context.routes)

        #: units that create their own Redux store
        self.private_stores: set[str] = set()

        self.index: SymbolIndex = context.symbols()

        self.liveness = Liveness(context)

        #: (file, function) → accesses it makes with the received key
        self.wrappers: dict[tuple[Path, str], set[Forward]] = {}

        #: the last name of each wrapper, so that only a call that may
        #: be one of them gets resolved
        self._wrapper_names: set[str] = set()

        #: (file, name) → the library function the name repeats
        self.aliases: dict[tuple[Path, str], tuple[libraries.StateLibrary, str]] = {}

    def extract(self) -> list[StateAccess]:

        self.private_stores = self._private_stores()

        files = [
            symbols
            for file_path in self.context.tree.source_files()
            if (symbols := self.index.of(file_path)) is not None
        ]

        for symbols in files:
            self._find_aliases(symbols)

        until_stable(files, self._find_wrappers)

        found: list[StateAccess] = []

        for symbols in files:
            found.extend(self._from_file(symbols.path, symbols))

        return sorted(
            found,
            key=lambda item: (
                item.microfrontend,
                item.path,
                item.at.file,
                item.at.line,
            ),
        )

    def _from_file(
        self,
        file_path: Path,
        symbols: ModuleSymbols,
    ) -> list[StateAccess]:

        owner = self.ownership.of_file(file_path)

        # An access in a shared package happens in each unit that
        # imports it (`shared`); otherwise, it belongs to no micro frontend.
        owners = [owner] if owner in self.known else sorted(self.shared.get(canonical(file_path), ()))

        if not owners:
            return []

        root, source = symbols.root, symbols.source

        bindings = self._bindings(symbols)

        relative = self.context.relative(file_path)

        found: list[StateAccess] = []

        def at(node: Node) -> SourceLocation:
            return SourceLocation(
                file=relative,
                line=node.start_point.row + 1,
                code=self._line(node, source),
            )

        for node in AstReader.find_all(root, "call_expression"):

            function = node.child_by_field_name("function")

            if not function:
                continue

            targets = self._targets(node, symbols)

            if targets:

                if not self.liveness.is_live(node, symbols):
                    continue

                for target in targets:

                    key = self._complete_key(target, symbols)

                    if key:
                        found.extend(
                            StateAccess(
                                microfrontend=owner,
                                library=target.kind,
                                path=key,
                                at=at(node),
                                access=target.access,
                            )
                            for owner in owners
                        )

                continue

            if function.type != "identifier":
                continue

            entry = bindings.get(AstReader.text(function, source))

            if not entry:
                continue

            library, kind = entry

            # A store created inside the unit itself is local state, even
            # if it uses the same library as the others.
            # A store created inside the unit itself is local state, even
            # if it uses the same library as the others.
            readers = [owner for owner in owners if not (library.module == "react-redux" and owner in self.private_stores)]

            if not readers or not self.liveness.is_live(node, symbols):
                continue

            for path in self._accesses(node, source, kind):

                found.extend(
                    StateAccess(
                        microfrontend=owner,
                        library=library.name,
                        path=path,
                        at=at(node),
                    )
                    for owner in readers
                )

        return found

    def _private_stores(self) -> set[str]:
        """The units in whose code a Redux store is created."""

        factories = set(libraries.REDUX_STORE_FACTORIES)

        found: set[str] = set()

        for file_path in self.context.tree.source_files():

            owner = self.ownership.of_file(file_path)

            if owner not in self.known or owner in found:
                continue

            try:
                root, source = self.context.reader.parse(file_path)
            except Exception:
                continue

            local = {
                record.local_name
                for record in ImportTable.records(root, source)
                if (record.module, record.imported_name) in factories
            }

            if not local:
                continue

            for node in AstReader.find_all(root, "call_expression"):

                function = node.child_by_field_name("function")

                if function is not None and AstReader.text(function, source) in local:
                    found.add(owner)
                    break

        return found

    # ------------------------------------------------------------------
    # Who is what in this file
    # ------------------------------------------------------------------

    def _bindings(self, symbols: ModuleSymbols) -> dict[str, tuple[libraries.StateLibrary, str]]:
        """
        Local name -> (library, role of the function).

        Both the library's import and that of a project name that only
        repeats it count: the `useAppSelector` that the Redux Toolkit
        documentation says to declare once and use instead of
        `useSelector`
        (https://redux.js.org/usage/usage-with-typescript#define-typed-hooks).
        """

        bindings = self._bindings_of_libraries(symbols)

        for local in symbols.imports:

            alias = None if local in bindings else self._alias_of(symbols, local)

            if alias:
                bindings[local] = alias

        for (path, name), alias in self.aliases.items():
            if path == symbols.path:
                bindings.setdefault(name, alias)

        return bindings

    def _alias_of(
        self,
        symbols: ModuleSymbols,
        local: str,
    ) -> tuple[libraries.StateLibrary, str] | None:
        """The library function behind a name imported from the project."""

        found = self.index.imported(symbols, local)

        if not found:
            return None

        path, imported = found

        target = self.index.of(path)

        if target is None:
            return None

        return self.aliases.get((target.path, target.exports.get(imported, imported)))

    def _find_aliases(self, symbols: ModuleSymbols) -> None:
        """
        `const useAppSelector = useSelector` and the Redux Toolkit 2 form,
        `useSelector.withTypes<RootState>()`: the declared name is the
        selector itself, with another type.
        """

        own = self._bindings_of_libraries(symbols)

        if not own:
            return

        for node in AstReader.find_all(symbols.root, "variable_declarator"):

            name = node.child_by_field_name("name")
            value = unwrap(node.child_by_field_name("value"))

            if name is None or value is None or name.type != "identifier":
                continue

            if value.type == "call_expression":

                function = unwrap(value.child_by_field_name("function"))
                member = function.child_by_field_name("property") if function is not None and function.type == "member_expression" else None

                if member is None or symbols.text(member) != "withTypes":
                    continue

                value = unwrap(function.child_by_field_name("object"))

            if value is None or value.type != "identifier":
                continue

            entry = own.get(symbols.text(value))

            if entry:
                self.aliases[(symbols.path, symbols.text(name))] = entry

    @staticmethod
    def _bindings_of_libraries(symbols: ModuleSymbols) -> dict[str, tuple[libraries.StateLibrary, str]]:
        """Only the names imported from the libraries, without the project's."""

        by_module = {library.module: library for library in libraries.STATE_LIBRARIES}

        bindings: dict[str, tuple[libraries.StateLibrary, str]] = {}

        for record in ImportTable.records(symbols.root, symbols.source):

            library = by_module.get(record.module)

            if not library:
                continue

            for kind, names in (("selector", library.selectors), ("atom", library.atoms)):
                if record.imported_name in names:
                    bindings[record.local_name] = (library, kind)

        return bindings

    # ------------------------------------------------------------------
    # Browser storage
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Browser storage
    # ------------------------------------------------------------------

    def _targets(self, node: Node, symbols: ModuleSymbols) -> list[Target]:
        """The storage accesses the call makes, directly or through a wrapper."""

        direct = self._storage(node, symbols)

        return [direct] if direct else self._wrapper_call(node, symbols)

    def _storage(self, node: Node, symbols: ModuleSymbols) -> Target | None:
        """
        `localStorage.setItem(chave, …)` and `getItem(chave)`.

        The receiver must be `localStorage` or `sessionStorage` itself:
        an arbitrary `cache.getItem("x")` is not shared storage, and
        matching only by method name would turn every class with
        `getItem` into global state.
        """

        function = unwrap(node.child_by_field_name("function"))

        if function is None or function.type != "member_expression":
            return None

        method = function.child_by_field_name("property")
        receiver = function.child_by_field_name("object")

        if not method or not receiver:
            return None

        name = symbols.text(method)

        if name not in libraries.STORAGE_WRITE + libraries.STORAGE_READ + libraries.STORAGE_CLEAR:
            return None

        # Accepts `localStorage` and `window.localStorage`.
        kind = symbols.text(receiver).rpartition(".")[2]

        if kind not in libraries.STORAGES:
            return None

        arguments = self._arguments(node)

        # `clear()` erases every key: it writes without saying which.
        if name in libraries.STORAGE_CLEAR:
            return Target(kind=kind, access="write", key=None)

        if not arguments:
            return None

        access = "write" if name in libraries.STORAGE_WRITE else "read"

        return Target(kind=kind, access=access, key=arguments[0])

    def _wrapper_call(self, node: Node, symbols: ModuleSymbols) -> list[Target]:
        """Call to a project function that forwards the key."""

        function = unwrap(node.child_by_field_name("function"))

        if function is None:
            return []

        name = function.child_by_field_name("property") if function.type == "member_expression" else function

        if name is None or symbols.text(name) not in self._wrapper_names:
            return []

        callee = self.index.callee(node, symbols)

        forwards = self.wrappers.get(callee, set()) if callee else set()

        arguments = self._arguments(node)

        return [
            Target(
                kind=forward.kind,
                access=forward.access,
                key=arguments[forward.index],
                prefix=forward.prefix,
                suffix=forward.suffix,
            )
            for forward in sorted(forwards, key=lambda item: (item.access, item.kind, item.index))
            if forward.index < len(arguments)
        ]

    def _find_wrappers(self, node: Node, symbols: ModuleSymbols) -> bool:
        """
        The enclosing function, if it forwards a parameter as the key.

        The key must be the parameter, with at most known text before
        and after it: `key`, `` `app:${key}` ``, `"pref." + key`.
        """

        found = False

        for target in self._targets(node, symbols):

            if target.key is None:
                continue

            parts = [target.prefix, *self._key_parts(target.key, symbols), target.suffix]

            tails = [index for index, part in enumerate(parts) if isinstance(part, Parameter)]

            if len(tails) != 1 or any(part is None for part in parts):
                continue

            parameter = parts[tails[0]]

            key = self.index.key_of(parameter.function, symbols)

            if key is None:
                continue

            forward = Forward(
                kind=target.kind,
                index=parameter.index,
                prefix="".join(parts[: tails[0]]),
                suffix="".join(parts[tails[0] + 1 :]),
                access=target.access,
            )

            forwards = self.wrappers.setdefault((symbols.path, key), set())

            if forward not in forwards:
                forwards.add(forward)
                self._wrapper_names.add(key.rpartition(".")[2])
                found = True

        return found

    def _complete_key(self, target: Target, symbols: ModuleSymbols) -> str | None:
        """
        The key, with `{param}` in place of each runtime segment.

        `` `${user.handle}_provider` `` is the same slice for every
        user: the contract is the key's format, like the path of a URL.
        With no known text at all — `getItem(key)` — there is no
        contract to record. A key that is a parameter of the enclosing
        function is read at its callers, not here.
        """

        if target.key is None:
            return libraries.ALL_KEYS

        parts = [target.prefix, *self._key_parts(target.key, symbols), target.suffix]

        if any(isinstance(part, Parameter) for part in parts):
            return None

        literal = "".join(part for part in parts if isinstance(part, str))

        if not any(character.isalnum() for character in literal):
            return None

        return "".join(PARAM if part is None else part for part in parts)

    def _key_parts(self, node: Node, symbols: ModuleSymbols) -> list[Part]:
        """
        The pieces of the key.

        Only a literal or a resolvable constant, never the identifier's
        name. The key is the contract: two units are coupled because
        they touch the SAME string. Falling back to the variable name
        joins any pair of files that, by coincidence, call theirs
        `storageKey` — which is what happened with two copied theme
        providers that had nothing to do with each other.

        The price is losing a key built in a variable. Worth it:
        inventing coupling is worse than missing one.
        """

        node = unwrap(node)

        if node is None:
            return [None]

        if node.type == "identifier":

            parameter = parameter_of(node, symbols)

            if parameter is not None:
                return [parameter]

        if node.type in ("string", "identifier", "template_string", "binary_expression"):

            key = self._key(node, symbols.source)

            if key is not None:
                return [key]

        if node.type == "template_string":
            return self._template_parts(node, symbols)

        if node.type == "binary_expression":

            operator = node.child_by_field_name("operator")

            if operator is None or symbols.text(operator) != "+":
                return [None]

            return self._key_parts(node.child_by_field_name("left"), symbols) + self._key_parts(
                node.child_by_field_name("right"), symbols
            )

        return [self._key(node, symbols.source)]

    def _template_parts(self, node: Node, symbols: ModuleSymbols) -> list[Part]:

        parts: list[Part] = []

        position = node.start_byte + 1

        for child in node.named_children:

            if child.type != "template_substitution":
                continue

            if child.start_byte > position:
                parts.append(symbols.source[position:child.start_byte].decode("utf-8", "replace"))

            inner = [item for item in child.named_children if item.type != "comment"]

            parts.extend(self._key_parts(inner[0], symbols) if inner else [None])

            position = child.end_byte

        if node.end_byte - 1 > position:
            parts.append(symbols.source[position:node.end_byte - 1].decode("utf-8", "replace"))

        return parts

    def _key(self, node: Node | None, source: bytes) -> str | None:

        if node is None:
            return None

        if node.type == "string":
            return AstReader.strip_quotes(AstReader.text(node, source))

        value = self.evaluator.evaluate(node, source)

        # Whole keys only: `"cart_" + id` does not say which slice it is,
        # and its beginning would merge different keys into one.
        if not value or value.match != EXACT or value.based:
            return None

        return value.url

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def _accesses(
        self,
        node: Node,
        source: bytes,
        kind: str,
    ) -> list[str]:

        arguments = self._arguments(node)

        if not arguments:
            return []

        if kind == "atom":

            name = AstReader.text(arguments[0], source).strip()

            return [name] if name.isidentifier() else []

        if kind == "selector":
            return self._paths(arguments[0], source)

        return []

    def _paths(self, selector: Node, source: bytes) -> list[str]:
        """
        The paths a selector walks.

        `(state) => state.cart` returns `cart`. A selector that builds
        an object — `(state) => ({ user: state.user, cart: state.cart })`
        — returns both: they are two slices read, not one.
        """

        parameter = self._first_parameter(selector, source)

        if not parameter:
            return []

        body = selector.child_by_field_name("body") or selector

        paths: list[str] = []

        for node in AstReader.find_all(body, "member_expression"):

            path = self._path_from(node, source, parameter)

            if path and path not in paths:
                paths.append(path)

        return paths

    @staticmethod
    def _first_parameter(selector: Node, source: bytes) -> str | None:

        if selector.type not in {
            "arrow_function",
            "function_expression",
            "function_declaration",
        }:
            return None

        parameter = selector.child_by_field_name("parameter")

        if parameter:
            return AstReader.text(parameter, source)

        parameters = selector.child_by_field_name("parameters")

        if not parameters:
            return None

        for child in parameters.named_children:

            if child.type == "identifier":
                return AstReader.text(child, source)

        return None

    @staticmethod
    def _path_from(
        node: Node,
        source: bytes,
        parameter: str,
    ) -> str | None:
        """
        `state.user.profile` becomes `user.profile`.

        Only the outermost expression matters: the inner ones are its
        prefixes and would count the same read twice.
        """

        if node.parent and node.parent.type == "member_expression":
            return None

        text = AstReader.text(node, source)

        head, _, rest = text.partition(".")

        if head.strip() != parameter or not rest:
            return None

        return rest.strip()

    # ------------------------------------------------------------------

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
    def _line(node: Node, source: bytes) -> str:

        return " ".join(AstReader.text(node, source).split())[:160]
