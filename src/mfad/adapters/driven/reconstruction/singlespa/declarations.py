"""
Onde um componente é definido.

O local de uma tela ou de um fragmento é a definição do componente:
o arquivo dele e a linha em que é declarado. A rota e o `export` que
o publicam ficam em outro arquivo, e juntar o arquivo de um com a
linha do outro dava um local que não existe.
"""

from __future__ import annotations

from pathlib import Path

from tree_sitter import Node

from mfad.adapters.driven.reconstruction.ast import AstReader
from mfad.adapters.driven.reconstruction.singlespa.exported_values import ExportedValues
from mfad.domain import MicroFrontend


#: Declarações com nome no topo do módulo.
NAMED = frozenset({
    "function_declaration", "generator_function_declaration", "class_declaration",
    "abstract_class_declaration",
})


def relocate(context, microfrontend: MicroFrontend) -> None:
    """Põe em cada tela e fragmento a linha da definição do componente, no arquivo dele."""

    values = ExportedValues(context.reader)

    for item, name in [(screen, screen.component) for screen in microfrontend.screens] + [
        (fragment, fragment.name) for fragment in microfrontend.fragments
    ]:

        if not item.file:
            continue

        path = context.repository / item.file

        # O arquivo pode ser um barril (`export { X } from "./x"`): o
        # componente está onde o reexport leva.
        origin = values.origin(path, name)

        if origin is not None and origin.resolve() != path.resolve():
            path = origin
            item.file = context.relative(origin)

        line = declaration_line(context, path, name)

        if line is not None:
            item.line = line


def declaration_line(context, path: Path, name: str) -> int | None:
    """
    A linha em que `path` declara `name`; sem esse nome, a do
    `export default`, que é o que o import padrão traz com outro nome.
    """

    try:
        root, source = context.reader.parse(path)
    except Exception:
        return None

    default = None

    for statement in root.named_children:

        node = statement

        if statement.type == "export_statement":

            if any(child.type == "default" for child in statement.children) and default is None:
                default = statement.start_point.row + 1

            node = statement.child_by_field_name("declaration") or statement

        found = _declares(node, name, source)

        if found is not None:
            return found.start_point.row + 1

    return default


def _declares(node: Node, name: str, source: bytes) -> Node | None:

    if node.type in NAMED:
        declared = node.child_by_field_name("name")
        return node if declared is not None and AstReader.text(declared, source) == name else None

    if node.type in ("lexical_declaration", "variable_declaration"):

        for declarator in node.named_children:

            target = declarator.child_by_field_name("name") if declarator.type == "variable_declarator" else None

            if target is not None and AstReader.text(target, source) == name:
                return declarator

    return None
