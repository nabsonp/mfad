"""Reading of JSX elements, shared by screens and fragments."""

from __future__ import annotations

from typing import Iterator

from tree_sitter import Node

from mfad.adapters.driven.reconstruction.ast import AstReader


def elements(root: Node) -> Iterator[tuple[Node, Node]]:
    """
    Walks the JSX elements of the tree.

    Returns `(element, opening tag)` pairs — in a self-closing element
    both are the same node.
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
    The element's attributes as text.

    The value of `x={expr}` comes as `expr`, without the braces — which
    is what allows resolving `path={routes.CART}` later.
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


#: Components that wrap a screen without being the screen.
#:
#: `<Suspense fallback={…}><Pacientes /></Suspense>` declares the
#: Pacientes screen; Suspense is the lazy boundary that remote loading
#: requires, and it appears in every route of a Module Federation host.
#: Keeping that name would make the same component the screen of every
#: route in the system.
#:
#: The list is short on purpose: only wrappers that the framework itself
#: defines. Project wrappers do not belong here — that would be a
#: repository convention, and then the leaf rule handles it.
WRAPPERS = {
    "Suspense",
    "ErrorBoundary",
    "React.Suspense",
    "Route",
    "Fragment",
    "React.Fragment",
}


def component_name(element_expression: str) -> str | None:
    """
    The component the route renders.

    `<Cart addProduct={...} />` returns `Cart`. When there is a wrapper,
    returns what is inside: what matters is what the route shows, not
    the machinery that puts it there.
    """

    names = _component_names(element_expression)

    if not names:
        return None

    for name in names:
        if name not in WRAPPERS:
            return name

    return names[0]


def _component_names(expression: str) -> list[str]:
    """
    The cited components, from the outermost to the innermost.

    Only tags with an uppercase initial are considered: HTML elements
    are lowercase, and a `<div>` inside a `fallback` is not a screen.
    """

    found = []

    text = expression

    while "<" in text:

        _, _, text = text.partition("<")

        text = text.lstrip()

        if text.startswith("/"):
            continue

        name = ""

        for character in text:

            if character.isalnum() or character in "_$.":
                name += character
            else:
                break

        if name and name[0].isupper():
            found.append(name)

    return found
