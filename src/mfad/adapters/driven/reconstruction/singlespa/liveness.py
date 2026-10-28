"""
Whether the code of a channel end can ever run.

`dispatchEvent` inside a function nobody calls communicates nothing,
but being in the micro frontend's file was enough to become an edge.
The criterion is the "unused symbol" one of compilers and linters,
restricted to what can be decided without executing:

- a NON-exported function with no reference in its own file is dead;
- an EXPORTED function is dead when its file is imported by others in
  the project and none of those imports brings in the name — neither
  by namespace, nor by `export *`, nor by `import()`/`require`, which
  can read any name.

A file that nothing in the project imports is left out of the second
rule: it may be the application's entry, a module exposed to the host
or a file loaded by the framework, and the consumer is not in the code
that was read. Class methods are left out too: the framework calls
`ngOnInit`, the template calls the handler, and none of that is an
import.
"""

from __future__ import annotations

from pathlib import Path

from tree_sitter import Node

from mfad.adapters.driven.reconstruction.ast import AstReader, ModuleResolver
from mfad.adapters.driven.reconstruction.ast.resolver import canonical
from mfad.adapters.driven.reconstruction.ast.symbols import (
    FUNCTION_TYPES,
    ModuleSymbols,
)
from mfad.adapters.driven.reconstruction.singlespa.context import ScanContext


#: Imported name that may be any name.
ANY = "*"


class Liveness:

    def __init__(self, context: ScanContext):

        self.context = context

        self.index = context.symbols()

        #: file → names some other file imports from it
        self._imported: dict[Path, set[str]] | None = None

        self._references: dict[tuple[Path, str], bool] = {}

    def is_live(self, node: Node, symbols: ModuleSymbols) -> bool:
        """Whether no named function enclosing the node is unused."""

        current = node.parent

        while current is not None:

            if current.type in FUNCTION_TYPES:

                key = self.index.key_of(current, symbols)

                if key and "." not in key and not self._used(symbols, key):
                    return False

            current = current.parent

        return True

    def _used(self, symbols: ModuleSymbols, name: str) -> bool:

        cache = (symbols.path, name)

        if cache not in self._references:
            self._references[cache] = self._referenced_here(symbols, name) or self._imported_elsewhere(
                symbols, name
            )

        return self._references[cache]

    @staticmethod
    def _referenced_here(symbols: ModuleSymbols, name: str) -> bool:
        """Some use of the name in the file besides the declaration itself."""

        for node in AstReader.walk(symbols.root):

            if node.type not in ("identifier", "shorthand_property_identifier"):
                continue

            if symbols.text(node) != name:
                continue

            parent = node.parent

            if parent is None:
                continue

            # The declaration is not a use, and `export { f }` only makes
            # the name visible — the user is the importer.
            if parent.type in ("function_declaration", "generator_function_declaration", "variable_declarator"):

                if parent.child_by_field_name("name") == node:
                    continue

            if parent.type == "export_specifier":
                continue

            return True

        return False

    def _imported_elsewhere(self, symbols: ModuleSymbols, name: str) -> bool:

        exported = [alias for alias, local in symbols.exports.items() if local == name]

        if not exported:
            return False

        # Exported as default: the name it is imported under can be anything.
        if "default" in exported:
            return True

        imported = self._imports().get(symbols.path)

        # Nothing in the project imports the file: the consumer is not
        # in the code that was read.
        if imported is None:
            return True

        return ANY in imported or any(alias in imported for alias in exported)

    def _imports(self) -> dict[Path, set[str]]:
        """For each project file, the names others import from it."""

        if self._imported is not None:
            return self._imported

        found: dict[Path, set[str]] = {}

        for file_path in self.context.tree.source_files():

            symbols = self.index.of(file_path)

            if symbols is None:
                continue

            for local, (module, imported) in symbols.imports.items():

                target = ModuleResolver.resolve(module, symbols.path) or self.context.package_entry(module)

                if target is not None:
                    found.setdefault(canonical(target), set()).add(imported)

            for module, names in self._other_imports(symbols):

                target = ModuleResolver.resolve(module, symbols.path) or self.context.package_entry(module)

                if target is not None:
                    found.setdefault(canonical(target), set()).update(names)

        self._imported = found

        return found

    @staticmethod
    def _other_imports(symbols: ModuleSymbols) -> list[tuple[str, set[str]]]:
        """`export … from`, `import()` and `require()`."""

        found: list[tuple[str, set[str]]] = []

        for node in AstReader.walk(symbols.root):

            if node.type == "export_statement":

                origin = node.child_by_field_name("source")

                if origin is None:
                    continue

                clause = [child for child in node.named_children if child.type == "export_clause"]

                names = (
                    {
                        symbols.text(name)
                        for specifier in clause[0].named_children
                        if specifier.type == "export_specifier"
                        and (name := specifier.child_by_field_name("name")) is not None
                    }
                    if clause
                    else {ANY}
                )

                found.append((AstReader.strip_quotes(symbols.text(origin)), names))

            elif node.type == "call_expression":

                function = node.child_by_field_name("function")
                arguments = node.child_by_field_name("arguments")

                if function is None or arguments is None:
                    continue

                if function.type != "import" and symbols.text(function) != "require":
                    continue

                strings = [child for child in arguments.named_children if child.type == "string"]

                if strings:
                    found.append((AstReader.strip_quotes(symbols.text(strings[0])), {ANY}))

        return found
