"""
Functions, classes and exports of a file, and what a call refers to.

Just enough of JavaScript's module semantics to follow a call to the
function it runs, within the project:

- `f()` is the function `f` of this file or the one imported under that name;
- `api.f()` is the member `f` of what `api` imports — the namespace
  (`import * as api`) or the object of `export default { f }`;
- `this.f()` is the method `f` of the enclosing class;
- `this.x.f()` is the method `f` of the class of `x`, when the type of `x`
  is written: a constructor parameter with a modifier
  (`constructor(private x: Servico)`), an annotated field (`x: Servico`) or
  `x = inject(Servico)`. This is how Angular injects dependencies, and the
  type is what the compiler itself uses to know what `x` is.

This is not type inference. What depends on runtime values
— a function stored in a variable, an object built dynamically — is left
without a target, and that is a legitimate answer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Node

from mfad.adapters.driven.reconstruction.ast.imports import ImportTable
from mfad.adapters.driven.reconstruction.ast.reader import AstReader
from mfad.adapters.driven.reconstruction.ast.resolver import ModuleResolver
from mfad.adapters.driven.reconstruction.ast.resolver import canonical


FUNCTION_TYPES = frozenset(
    {
        "function_declaration",
        "generator_function_declaration",
        "function_expression",
        "function",
        "generator_function",
        "arrow_function",
        "method_definition",
    }
)

#: Nodes that only wrap a value, without changing what it is.
WRAPPERS = frozenset(
    {
        "as_expression",
        "satisfies_expression",
        "non_null_expression",
        "parenthesized_expression",
        "type_assertion",
    }
)


def unwrap(node: Node | None) -> Node | None:
    """`x as T`, `x!`, `(x)` count as `x`."""

    while node is not None and node.type in WRAPPERS:

        inner = [child for child in node.named_children if child.type != "comment"]

        if not inner:
            return node

        node = inner[0]

    return node


def declared_value(identifier: Node, source: bytes) -> Node | None:
    """
    The value the variable was declared with, in the scope of the use.

    Walks up the blocks enclosing the use and, in each one, takes the
    closest same-name declaration BEFORE the use. Stops at the
    first block that has one: that is the one the scoping rule sees.
    """

    name = AstReader.text(identifier, source)

    scope = identifier.parent

    while scope is not None:

        if scope.type in ("statement_block", "program"):

            candidates = [
                declarator
                for declarator in AstReader.find_all(scope, "variable_declarator")
                if declarator.start_byte < identifier.start_byte
                and (found := declarator.child_by_field_name("name")) is not None
                and AstReader.text(found, source) == name
            ]

            if candidates:
                return unwrap(
                    max(candidates, key=lambda item: item.start_byte).child_by_field_name("value")
                )

        scope = scope.parent

    return None


def parameters(function: Node, source: bytes) -> list[str]:
    """The parameter names, in order; empty where there is no simple name."""

    single = function.child_by_field_name("parameter")

    if single is not None:
        return [AstReader.text(single, source)]

    container = function.child_by_field_name("parameters")

    if container is None:
        return []

    names: list[str] = []

    for child in container.named_children:

        if child.type == "comment":
            continue

        names.append(_parameter_name(child, source))

    return names


def _parameter_name(node: Node, source: bytes) -> str:

    if node.type == "identifier":
        return AstReader.text(node, source)

    # `x = default` in JavaScript
    if node.type == "assignment_pattern":
        left = node.child_by_field_name("left")
        return _parameter_name(left, source) if left is not None else ""

    # `x: T`, `x?: T`, `x = default` in TypeScript
    if node.type in ("required_parameter", "optional_parameter"):
        pattern = node.child_by_field_name("pattern")
        return _parameter_name(pattern, source) if pattern is not None else ""

    return ""


def returned_expression(function: Node) -> Node | None:
    """
    The expression the function returns, when that is all it does.

    `(id) => \\`/users/${id}\\`` or a body with a single `return`.
    A body with more than one path has no SINGLE expression to return.
    """

    body = function.child_by_field_name("body")

    if body is None:
        return None

    if body.type != "statement_block":
        return unwrap(body)

    returns = list(AstReader.find_all(body, "return_statement"))

    statements = [child for child in body.named_children if child.type != "comment"]

    if len(returns) != 1 or len(statements) != 1 or statements[0] is not returns[0]:
        return None

    value = [child for child in returns[0].named_children if child.type != "comment"]

    return unwrap(value[0]) if value else None


def _type_name(annotation: Node | None, source: bytes) -> str | None:
    """`Servico` from `: Servico` or from `: Servico<T>`."""

    if annotation is None:
        return None

    for child in annotation.named_children:

        if child.type == "type_identifier":
            return AstReader.text(child, source)

        if child.type == "generic_type":
            name = child.child_by_field_name("name")
            return AstReader.text(name, source) if name is not None else None

    return None


def _injected(value: Node | None, source: bytes) -> str | None:
    """`inject(Servico)` → `Servico`."""

    value = unwrap(value)

    if value is None or value.type != "call_expression":
        return None

    function = value.child_by_field_name("function")
    arguments = value.child_by_field_name("arguments")

    if function is None or arguments is None or AstReader.text(function, source) != "inject":
        return None

    named = [child for child in arguments.named_children if child.type != "comment"]

    if not named or named[0].type != "identifier":
        return None

    return AstReader.text(named[0], source)


@dataclass
class Function:
    """A named function reachable by a call."""

    key: str
    node: Node
    parameters: list[str]


@dataclass
class ModuleSymbols:
    """What a file declares and imports."""

    path: Path
    root: Node
    source: bytes

    #: local name → (specifier, imported name); `default` and `*`
    #: for default and namespace imports
    imports: dict[str, tuple[str, str]] = field(default_factory=dict)

    #: key → function. The key is the name (`f`), `Classe.metodo` or
    #: `default.membro` for a method written inside the `export default`.
    functions: dict[str, Function] = field(default_factory=dict)

    #: exported name → local key. `default` and `default.membro`
    #: for the default export and the members of the exported object.
    exports: dict[str, str] = field(default_factory=dict)

    #: class → field → type name
    fields: dict[str, dict[str, str]] = field(default_factory=dict)

    #: `export { a as b } from "./x"` and `export * from "./x"`: the
    #: specifier and exported name → name there (`None` for `*`)
    reexports: list[tuple[str, dict[str, str] | None]] = field(default_factory=list)

    #: function node id → key
    keys: dict[int, str] = field(default_factory=dict)

    def text(self, node: Node) -> str:
        return AstReader.text(node, self.source)


class SymbolIndex:
    """The symbols of each file, read once, and call resolution."""

    def __init__(self, reader: AstReader, packages: Callable[[str], Path | None] | None = None):

        self.reader = reader

        #: the entry file of a package from the corpus itself
        self.packages = packages

        self._modules: dict[Path, ModuleSymbols | None] = {}
        self._imported: dict[tuple[Path, str], tuple[Path, str] | None] = {}

    def of(self, path: Path) -> ModuleSymbols | None:

        # By the resolved form: the same file arrives through the scan and
        # through import resolution, and the keys must match.
        path = canonical(path)

        if path in self._modules:
            return self._modules[path]

        try:
            root, source = self.reader.parse(path)
        except Exception:
            self._modules[path] = None
            return None

        symbols = ModuleSymbols(path=path, root=root, source=source)

        self._read(symbols)

        self._modules[path] = symbols

        return symbols

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def _read(self, symbols: ModuleSymbols) -> None:

        for record in ImportTable.records(symbols.root, symbols.source):
            symbols.imports[record.local_name] = (record.module, record.imported_name)

        for node in AstReader.walk(symbols.root):

            if node.type in FUNCTION_TYPES:

                key = self._key(node, symbols)

                if key:
                    symbols.keys[node.id] = key
                    symbols.functions.setdefault(
                        key, Function(key=key, node=node, parameters=parameters(node, symbols.source))
                    )

            elif node.type == "class_declaration" or node.type == "class":
                self._fields(node, symbols)

            elif node.type == "export_statement":
                self._exports(node, symbols)

    def _key(self, node: Node, symbols: ModuleSymbols) -> str | None:

        name = node.child_by_field_name("name")

        if node.type == "method_definition":

            owner = self._class_name(node, symbols)

            if name is None:
                return None

            if owner:
                return f"{owner}.{symbols.text(name)}"

            # Method written in the object of `export default { get() {…} }`.
            if self._default_object(node.parent):
                return f"default.{symbols.text(name)}"

            return None

        if name is not None and node.type in ("function_declaration", "generator_function_declaration"):
            return symbols.text(name)

        parent = node.parent

        if parent is None:
            return None

        # `const f = () => …`
        if parent.type == "variable_declarator":
            target = parent.child_by_field_name("name")
            return symbols.text(target) if target is not None and target.type == "identifier" else None

        # `class C { f = () => … }`
        if parent.type == "public_field_definition":

            owner = self._class_name(parent, symbols)
            target = parent.child_by_field_name("name")

            if owner and target is not None:
                return f"{owner}.{symbols.text(target)}"

        # `export default { get: () => … }`
        if parent.type == "pair" and self._default_object(parent.parent):

            target = parent.child_by_field_name("key")

            if target is not None:
                return f"default.{AstReader.strip_quotes(symbols.text(target))}"

        return None

    @staticmethod
    def _class_name(node: Node, symbols: ModuleSymbols) -> str | None:

        body = node.parent

        if body is None or body.type != "class_body" or body.parent is None:
            return None

        name = body.parent.child_by_field_name("name")

        return symbols.text(name) if name is not None else None

    @staticmethod
    def _default_object(node: Node | None) -> bool:

        return (
            node is not None
            and node.type == "object"
            and node.parent is not None
            and node.parent.type == "export_statement"
            and any(child.type == "default" for child in node.parent.children)
        )

    def _fields(self, node: Node, symbols: ModuleSymbols) -> None:

        name = node.child_by_field_name("name")
        body = node.child_by_field_name("body")

        if name is None or body is None:
            return

        typed = symbols.fields.setdefault(symbols.text(name), {})

        for member in body.named_children:

            if member.type == "public_field_definition":

                target = member.child_by_field_name("name")

                kind = _type_name(member.child_by_field_name("type"), symbols.source) or _injected(
                    member.child_by_field_name("value"), symbols.source
                )

                if target is not None and kind:
                    typed[symbols.text(target)] = kind

            elif member.type == "method_definition":

                method = member.child_by_field_name("name")

                if method is None or symbols.text(method) != "constructor":
                    continue

                container = member.child_by_field_name("parameters")

                for parameter in container.named_children if container is not None else []:

                    # Only a parameter with a modifier becomes a field: it is
                    # TypeScript's "parameter property".
                    if parameter.type not in ("required_parameter", "optional_parameter"):
                        continue

                    if not any(
                        child.type in ("accessibility_modifier", "readonly", "override_modifier")
                        for child in parameter.children
                    ):
                        continue

                    pattern = parameter.child_by_field_name("pattern")
                    kind = _type_name(parameter.child_by_field_name("type"), symbols.source)

                    if pattern is not None and pattern.type == "identifier" and kind:
                        typed[symbols.text(pattern)] = kind

    def _exports(self, node: Node, symbols: ModuleSymbols) -> None:

        origin = node.child_by_field_name("source")

        if origin is not None:

            clause = [child for child in node.named_children if child.type == "export_clause"]

            names = {
                symbols.text(specifier.child_by_field_name("alias") or name): symbols.text(name)
                for specifier in (clause[0].named_children if clause else [])
                if specifier.type == "export_specifier" and (name := specifier.child_by_field_name("name")) is not None
            }

            symbols.reexports.append((AstReader.strip_quotes(symbols.text(origin)), names if clause else None))

            return

        is_default = any(child.type == "default" for child in node.children)

        declaration = node.child_by_field_name("declaration")

        if declaration is not None:

            names: list[str] = []

            if declaration.type in ("lexical_declaration", "variable_declaration"):
                names = [
                    symbols.text(target)
                    for declarator in declaration.named_children
                    if declarator.type == "variable_declarator"
                    and (target := declarator.child_by_field_name("name")) is not None
                    and target.type == "identifier"
                ]

            elif (target := declaration.child_by_field_name("name")) is not None:
                names = [symbols.text(target)]

            for name in names:
                symbols.exports[name] = name

            if is_default and names:
                symbols.exports["default"] = names[0]

            return

        value = unwrap(node.child_by_field_name("value"))

        if is_default and value is not None:

            if value.type == "identifier":
                symbols.exports["default"] = symbols.text(value)

            elif value.type == "object":

                for member in value.named_children:

                    if member.type == "shorthand_property_identifier":
                        symbols.exports[f"default.{symbols.text(member)}"] = symbols.text(member)

                    elif member.type == "pair":

                        key = member.child_by_field_name("key")
                        target = member.child_by_field_name("value")

                        if key is None or target is None:
                            continue

                        member_name = AstReader.strip_quotes(symbols.text(key))

                        symbols.exports[f"default.{member_name}"] = (
                            symbols.text(target)
                            if target.type == "identifier"
                            else f"default.{member_name}"
                        )

                    elif member.type == "method_definition":

                        method = member.child_by_field_name("name")

                        if method is not None:
                            symbols.exports[f"default.{symbols.text(method)}"] = f"default.{symbols.text(method)}"

            return

        # `export { a, b as c }`
        for clause in node.named_children:

            if clause.type != "export_clause":
                continue

            for specifier in clause.named_children:

                if specifier.type != "export_specifier":
                    continue

                local = specifier.child_by_field_name("name")
                alias = specifier.child_by_field_name("alias")

                if local is None:
                    continue

                symbols.exports[symbols.text(alias if alias is not None else local)] = symbols.text(local)

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def enclosing_class(self, node: Node, symbols: ModuleSymbols) -> str | None:

        current = node.parent

        while current is not None:

            if current.type in ("class_declaration", "class"):
                name = current.child_by_field_name("name")
                return symbols.text(name) if name is not None else None

            current = current.parent

        return None

    def exported(self, path: Path, name: str, depth: int = 0) -> tuple[Path, str] | None:
        """
        The function that `path` exports as `name`, as (file, key).

        A name the file only passes along — `export * from "./x"`, the
        `index` of every library — is looked up in the file it comes from.
        """

        symbols = self.of(path)

        if symbols is None:
            return None

        local = symbols.exports.get(name, name)

        if name in symbols.exports or local in symbols.functions or depth >= 5:
            return path, local

        head = name.split(".")[0]

        for module, names in symbols.reexports:

            if names is not None and head not in names:
                continue

            target = ModuleResolver.resolve(module, symbols.path)

            if target is None:
                continue

            renamed = name if names is None else names[head] + name[len(head):]

            found = self.exported(canonical(target), renamed, depth + 1)

            if found is not None and (names is not None or self._declares(*found)):
                return found

        return path, local

    def _declares(self, path: Path, key: str) -> bool:

        symbols = self.of(path)

        return symbols is not None and (key in symbols.functions or key in symbols.exports)

    def imported(self, symbols: ModuleSymbols, local: str) -> tuple[Path, str] | None:
        """The project file and the imported name behind a local name."""

        cache = (symbols.path, local)

        if cache in self._imported:
            return self._imported[cache]

        result = None

        found = symbols.imports.get(local)

        if found is not None:

            module, imported = found

            target = ModuleResolver.resolve(module, symbols.path)

            # `import { usePerson } from "@org/common"`, with the package in
            # the corpus: the called function is that package's.
            if target is None and self.packages is not None:
                target = self.packages(module)

            result = (canonical(target), imported) if target is not None else None

        self._imported[cache] = result

        return result

    def callee(self, call: Node, symbols: ModuleSymbols) -> tuple[Path, str] | None:
        """The function the call runs, as (file, key)."""

        function = unwrap(call.child_by_field_name("function"))

        if function is None:
            return None

        if function.type == "identifier":

            name = symbols.text(function)

            if name in symbols.functions:
                return symbols.path, name

            found = self.imported(symbols, name)

            return self.exported(*found) if found else None

        if function.type != "member_expression":
            return None

        receiver = unwrap(function.child_by_field_name("object"))
        member = function.child_by_field_name("property")

        if receiver is None or member is None:
            return None

        method = symbols.text(member)

        # `this.metodo()`
        if receiver.type == "this":

            owner = self.enclosing_class(call, symbols)

            return (symbols.path, f"{owner}.{method}") if owner else None

        # `this.servico.metodo()`
        if receiver.type == "member_expression":

            holder = receiver.child_by_field_name("object")
            name = receiver.child_by_field_name("property")

            if holder is None or name is None or holder.type != "this":
                return None

            owner = self.enclosing_class(call, symbols)

            kind = symbols.fields.get(owner or "", {}).get(symbols.text(name))

            return self.of_class(symbols, kind, method) if kind else None

        # `api.metodo()`, with `api` imported
        if receiver.type == "identifier":

            found = self.imported(symbols, symbols.text(receiver))

            if not found:
                return None

            path, imported = found

            if imported == "*":
                return self.exported(path, method)

            if imported == "default":
                return self.exported(path, f"default.{method}")

            # `import { Servico }` and static `Servico.metodo()`
            return path, f"{imported}.{method}"

        return None

    def of_class(self, symbols: ModuleSymbols, kind: str, method: str) -> tuple[Path, str] | None:
        """The method of a class declared here or imported."""

        key = f"{kind}.{method}"

        if key in symbols.functions:
            return symbols.path, key

        found = self.imported(symbols, kind)

        if not found:
            return None

        path, imported = found

        target = self.of(path)

        if target is None:
            return None

        name = target.exports.get(imported, imported) if imported != "default" else target.exports.get("default", "")

        return path, f"{name}.{method}"

    def function(self, path: Path, key: str) -> Function | None:

        symbols = self.of(path)

        return symbols.functions.get(key) if symbols else None

    def key_of(self, function: Node, symbols: ModuleSymbols) -> str | None:
        return symbols.keys.get(function.id)
