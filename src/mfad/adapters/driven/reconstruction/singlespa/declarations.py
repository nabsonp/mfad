"""
Where a component is defined.

The location of a screen or a fragment is the component's definition:
its file and the line where it is declared. The route and the `export`
that publish it are in another file, and combining the file of one with
the line of the other produced a location that does not exist.
"""

from __future__ import annotations

from pathlib import Path

from tree_sitter import Node

from mfad.adapters.driven.reconstruction.ast import AstReader
from mfad.adapters.driven.reconstruction.singlespa.exported_values import ExportedValues
from mfad.domain import MicroFrontend


#: Named declarations at the top of the module.
NAMED = frozenset({
    "function_declaration", "generator_function_declaration", "class_declaration",
    "abstract_class_declaration",
})


def relocate(context, microfrontend: MicroFrontend) -> None:
    """Gives each screen and fragment the line of the component's definition, in its own file."""

    values = ExportedValues(context.reader)

    for item, name in [(screen, screen.component) for screen in microfrontend.screens] + [
        (fragment, fragment.name) for fragment in microfrontend.fragments
    ]:

        if not item.file:
            continue

        path = context.repository / item.file

        # The file may be a barrel (`export { X } from "./x"`): the
        # component is where the re-export leads.
        origin = values.origin(path, name)

        if origin is not None and origin.resolve() != path.resolve():
            path = origin
            item.file = context.relative(origin)

        line = declaration_line(context, path, name)

        if line is not None:
            item.line = line


def declaration_line(context, path: Path, name: str) -> int | None:
    """
    The line where `path` declares `name`; without that name, the line
    of the `export default`, which is what the default import brings in
    under another name.
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
