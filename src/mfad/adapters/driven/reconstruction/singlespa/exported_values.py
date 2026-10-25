"""
O que um nome exportado é: componente ou dado.

Fragmento é componente publicado para outro micro frontend montar.
Componente, no React, é função ou classe (https://react.dev/reference/react/Component);
no Angular, classe; no Vue, também o objeto de opções
(https://vuejs.org/api/options-state.html). Um objeto de textos, uma
lista, um número ou um tipo do TypeScript saem pelo mesmo `export`,
mas ninguém os monta: não são fragmento.

Segue o nome pelos `export ... from` e pelos `import` do projeto até a
declaração. O que não dá para seguir — pacote externo, valor montado
em tempo de execução, chamada de função — fica como componente: é a
resposta de antes, e errar para menos esconderia um fragmento real.
"""

from __future__ import annotations

from pathlib import Path

from tree_sitter import Node

from mfad.adapters.driven.reconstruction.ast import AstReader, ModuleResolver
from mfad.adapters.driven.reconstruction.ast.symbols import unwrap


#: Valores que não são componente em framework nenhum.
DATA = frozenset({
    "string", "template_string", "number", "true", "false", "null",
    "undefined", "array", "regex",
})

#: Declarações que só existem para o compilador do TypeScript, ou
#: valores que não se montam (`enum`).
NOT_COMPONENT_DECLARATIONS = frozenset({
    "interface_declaration", "type_alias_declaration", "enum_declaration",
})

#: Opções sem as quais um objeto Vue não mostra nada: o modelo, a
#: função de renderização ou o `setup` que a devolve
#: (https://vuejs.org/api/options-rendering.html). `components` sozinho
#: não basta: um objeto de textos também tem uma chave assim.
VUE_OPTIONS = frozenset({"render", "template", "setup"})

MAX_DEPTH = 8


class ExportedValues:

    def __init__(self, reader):
        self.reader = reader
        self._where: Path | None = None

    def is_data(self, path: Path, name: str) -> bool:
        """Se o que `path` exporta como `name` é, com certeza, dado e não componente."""

        return self._kind(path, name, 0, set()) == "data"

    def origin(self, path: Path, name: str) -> Path | None:
        """O arquivo que declara o que `path` exporta como `name`, seguindo os reexports."""

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

        # `export * from "./x"`: o nome pode estar em qualquer um.
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
        """O tipo do nome, se esta declaração o exporta; `False` se não exporta."""

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

        # `export * as ns from "./x"` exporta o objeto de namespace do
        # módulo (https://tc39.es/ecma262/#sec-module-namespace-objects):
        # não é função nem classe, ninguém o monta.
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
        """O tipo de um nome declarado ou importado no topo do módulo."""

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
        """O nome exportado por trás do nome local `name`, se este import o cria."""

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

        # Chamada (`memo(...)`, `lazy(...)`, `defineComponent(...)`) e o
        # resto: não dá para saber sem executar.
        return None
