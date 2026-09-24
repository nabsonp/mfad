"""Leitura de elementos JSX, compartilhada por telas e fragmentos."""

from __future__ import annotations

from typing import Iterator

from tree_sitter import Node

from damfe.adapters.driven.reconstruction.ast import AstReader


def elements(root: Node) -> Iterator[tuple[Node, Node]]:
    """
    Percorre os elementos JSX da árvore.

    Devolve pares `(elemento, tag de abertura)` — em um
    elemento auto-fechado os dois são o mesmo nó.
    """

    for node in AstReader.walk(root):

        if node.type == "jsx_self_closing_element":
            yield node, node

        elif node.type == "jsx_element":

            opening = node.child_by_field_name("open_tag")

            if opening:
                yield node, opening


def tag_name(opening: Node, source: bytes) -> str | None:

    name_node = opening.child_by_field_name("name")

    if not name_node:
        return None

    return AstReader.text(name_node, source)


def attributes(opening: Node, source: bytes) -> dict[str, str]:
    """
    Atributos do elemento como texto.

    O valor de `x={expr}` vem como `expr`, sem as chaves —
    é o que permite resolver `path={routes.CART}` depois.
    """

    found: dict[str, str] = {}

    for child in opening.named_children:

        if child.type != "jsx_attribute":
            continue

        parts = child.named_children

        if not parts:
            continue

        key = AstReader.text(parts[0], source)

        if len(parts) < 2:
            found[key] = ""
            continue

        value = parts[1]

        if value.type == "jsx_expression":

            inner = [
                node
                for node in value.named_children
                if node.type != "comment"
            ]

            found[key] = (
                AstReader.text(inner[0], source) if inner else ""
            )

        else:
            found[key] = AstReader.text(value, source)

    return found


def prop_names(opening: Node, source: bytes) -> list[str]:

    names: list[str] = []

    for child in opening.named_children:

        if child.type == "jsx_attribute":

            parts = child.named_children

            if parts:
                names.append(AstReader.text(parts[0], source))

        # <X {...props} />
        elif child.type == "jsx_expression":
            names.append("...")

    return names


def component_name(element_expression: str) -> str | None:
    """Extrai `Cart` de `<Cart addProduct={...} />`."""

    text = element_expression.strip()

    if not text.startswith("<"):
        return None

    text = text[1:].lstrip()

    name = ""

    for character in text:

        if character.isalnum() or character in "_$.":
            name += character
        else:
            break

    return name or None
