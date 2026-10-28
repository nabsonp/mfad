"""
What an exported name is: component or data.

A fragment is a component published for another micro frontend to
mount. A component, in React, is a function or a class
(https://react.dev/reference/react/Component); in Angular, a class; in
Vue, also the options object
(https://vuejs.org/api/options-state.html). A texts object, a list, a
number or a TypeScript type leave through the same `export`, but nobody
mounts them: they are not fragments.

Follows the name through the project's `export ... from` and `import`
statements up to the declaration. What cannot be followed — external
package, value built at runtime, function call — stays a component: it
is the previous answer, and erring on the low side would hide a real
fragment.
"""

from __future__ import annotations

from pathlib import Path

from tree_sitter import Node

from mfad.adapters.driven.reconstruction.ast import AstReader, ModuleResolver
from mfad.adapters.driven.reconstruction.ast.symbols import unwrap


#: Values that are not a component in any framework.
DATA = frozenset({
    "string", "template_string", "number", "true", "false", "null",
    "undefined", "array", "regex",
})

#: Declarations that exist only for the TypeScript compiler, or values
#: that cannot be mounted (`enum`).
NOT_COMPONENT_DECLARATIONS = frozenset({
    "interface_declaration", "type_alias_declaration", "enum_declaration",
})

#: Options without which a Vue object shows nothing: the template, the
#: render function or the `setup` that returns it
#: (https://vuejs.org/api/options-rendering.html). `components` alone
#: is not enough: a texts object can also have such a key.
VUE_OPTIONS = frozenset({"render", "template", "setup"})

MAX_DEPTH = 8


class ExportedValues:

    def __init__(self, reader):
        self.reader = reader
        self._where: Path | None = None

    def is_data(self, path: Path, name: str) -> bool:
        """Whether what `path` exports as `name` is, for sure, data and not a component."""

        return self._kind(path, name, 0, set()) == "data"

    def origin(self, path: Path, name: str) -> Path | None:
        """The file that declares what `path` exports as `name`, following the re-exports."""

        self._where = None
        self._kind(path, name, 0, set())

        return self._where

    # ------------------------------------------------------------------

    def _kind(self, path: Path, name: str, depth: int, seen: set) -> str | None:

        if depth > MAX_DEPTH or (path, name) in seen:
            return None

        seen.add((path, name))

        try:
            root, source = self.reader.parse(path)
        except Exception:
            return None

        for statement in root.named_children:

            if statement.type != "export_statement":
                continue

            found = self._from_export(statement, path, root, source, name, depth, seen)

            if found is not False:
                return found

        # `export * from "./x"`: the name may be in any of them.
        for statement in root.named_children:

            if statement.type != "export_statement" or name == "default":
                continue

            module = statement.child_by_field_name("source")

            if module is None or any(child.type in ("export_clause", "namespace_export") for child in statement.named_children):
                continue

            target = ModuleResolver.resolve(AstReader.strip_quotes(AstReader.text(module, source)), path)

            if target is not None:
                found = self._kind(target, name, depth + 1, seen)
                if found is not None:
                    return found

        return None

    def _from_export(self, statement, path, root, source, name, depth, seen):
        """The kind of the name, if this declaration exports it; `False` if it does not."""

        is_default = any(child.type == "default" for child in statement.children)

        declaration = statement.child_by_field_name("declaration")

        if declaration is not None:

            if declaration.type in ("lexical_declaration", "variable_declaration"):

                for declarator in declaration.named_children:

                    target = declarator.child_by_field_name("name") if declarator.type == "variable_declarator" else None

                    if target is not None and AstReader.text(target, source) == name:
                        return self._value(unwrap(declarator.child_by_field_name("value")), path, root, source, depth, seen)

                return False

            declared = declaration.child_by_field_name("name")

            if (declared is not None and AstReader.text(declared, source) == name) or (is_default and name == "default"):
                self._where = path
                return "data" if declaration.type in NOT_COMPONENT_DECLARATIONS else "component"

            return False

        if is_default:

            if name != "default":
                return False

            return self._value(unwrap(statement.child_by_field_name("value")), path, root, source, depth, seen)

        module = statement.child_by_field_name("source")

        # `export * as ns from "./x"` exports the module's namespace
        # object (https://tc39.es/ecma262/#sec-module-namespace-objects):
        # it is neither a function nor a class, nobody mounts it.
        for clause in statement.named_children:

            if clause.type == "namespace_export" and any(
                AstReader.text(child, source) == name for child in clause.named_children
            ):
                self._where = path
                return "data"

        for clause in statement.named_children:

            if clause.type != "export_clause":
                continue

            for specifier in clause.named_children:

                if specifier.type != "export_specifier":
                    continue

                local = specifier.child_by_field_name("name")
                alias = specifier.child_by_field_name("alias")

                if local is None or AstReader.text(alias if alias is not None else local, source) != name:
                    continue

                original = AstReader.text(local, source)

                # `export { a as b } from "./x"`
                if module is not None:
                    target = ModuleResolver.resolve(AstReader.strip_quotes(AstReader.text(module, source)), path)
                    return self._kind(target, original, depth + 1, seen) if target is not None else None

                return self._local(original, path, root, source, depth, seen)

        return False

    def _local(self, name, path, root, source, depth, seen):
        """The kind of a name declared or imported at the top of the module."""

        for statement in root.named_children:

            node = statement.child_by_field_name("declaration") if statement.type == "export_statement" else statement

            if node is None:
                continue

            if node.type in ("lexical_declaration", "variable_declaration"):

                for declarator in node.named_children:

                    target = declarator.child_by_field_name("name") if declarator.type == "variable_declarator" else None

                    if target is not None and AstReader.text(target, source) == name:
                        return self._value(unwrap(declarator.child_by_field_name("value")), path, root, source, depth, seen)

            elif (declared := node.child_by_field_name("name")) is not None and AstReader.text(declared, source) == name:
                self._where = path
                return "data" if node.type in NOT_COMPONENT_DECLARATIONS else "component"

            elif node.type == "import_statement":

                imported = self._imported(node, name, source)

                if imported is not None:
                    module = node.child_by_field_name("source")
                    target = ModuleResolver.resolve(AstReader.strip_quotes(AstReader.text(module, source)), path) if module is not None else None
                    return self._kind(target, imported, depth + 1, seen) if target is not None else None

        return None

    @staticmethod
    def _imported(statement: Node, name: str, source: bytes) -> str | None:
        """The exported name behind the local name `name`, if this import creates it."""

        for clause in statement.named_children:

            if clause.type != "import_clause":
                continue

            for child in clause.named_children:

                if child.type == "identifier" and AstReader.text(child, source) == name:
                    return "default"

                if child.type == "named_imports":

                    for specifier in child.named_children:

                        local = specifier.child_by_field_name("alias") or specifier.child_by_field_name("name")

                        if local is not None and AstReader.text(local, source) == name:
                            return AstReader.text(specifier.child_by_field_name("name"), source)

        return None

    def _value(self, value: Node | None, path, root, source, depth, seen) -> str | None:

        if value is None:
            return None

        if value.type != "identifier":
            self._where = path

        if value.type in DATA:
            return "data"

        if value.type == "object":

            keys = set()

            for member in value.named_children:

                key = member.child_by_field_name("key") if member.type == "pair" else member.child_by_field_name("name")

                if member.type == "shorthand_property_identifier":
                    keys.add(AstReader.text(member, source))
                elif key is not None:
                    keys.add(AstReader.strip_quotes(AstReader.text(key, source)))

            return "component" if keys & VUE_OPTIONS else "data"

        if value.type == "identifier":
            return self._local(AstReader.text(value, source), path, root, source, depth + 1, seen)

        if value.type in ("arrow_function", "function", "function_expression", "class"):
            return "component"

        # A call (`memo(...)`, `lazy(...)`, `defineComponent(...)`) and
        # the rest: there is no way to know without executing.
        return None
