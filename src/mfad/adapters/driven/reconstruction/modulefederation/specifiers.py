"""
Remote specifiers: how a file names the module of another unit.

`hs-pharmacy/Pharmacy` means the module `./Pharmacy` published by the
unit `hs-pharmacy`. The same specifier appears in static imports and in
dynamic `import()`, and both must be read — the dynamic one is how a
host loads a remote page.

It lives on its own because two stages depend on it: the extraction of
fragment consumption and the assignment of screens to their provider.
"""

from __future__ import annotations

from tree_sitter import Node

from mfad.adapters.driven.reconstruction.ast import AstReader


def dynamic_imports(
    root: Node,
    source: bytes,
) -> list[tuple[str, str, int, str]]:
    """
    `const Pharmacy = lazy(() => import("hs-pharmacy/Pharmacy"))`.

    Return (module, local name, line, code). The local name comes from
    the declaration that wraps the call, which is how the component is
    referenced later; without a declaration, it falls back to the last
    segment of the specifier.
    """

    found = []

    for call in AstReader.find_all(root, "call_expression"):

        function = call.child_by_field_name("function")

        if not function or AstReader.text(function, source) != "import":
            continue

        arguments = call.child_by_field_name("arguments")

        if not arguments:
            continue

        literals = [
            child
            for child in arguments.named_children
            if child.type == "string"
        ]

        if not literals:
            continue

        module = AstReader.strip_quotes(
            AstReader.text(literals[0], source)
        )

        found.append(
            (
                module,
                binding(call, source) or module.split("/")[-1],
                call.start_point.row + 1,
                AstReader.text(call, source).strip(),
            )
        )

    return found


def binding(node: Node, source: bytes) -> str | None:
    """The declared name that wraps the call, if any."""

    current = node.parent

    while current is not None:

        if current.type == "variable_declarator":

            name = current.child_by_field_name("name")

            return AstReader.text(name, source) if name else None

        if current.type in ("statement_block", "program"):
            return None

        current = current.parent

    return None


def split(module: str, catalog: dict[str, set[str]]) -> tuple[str | None, str]:
    """
    `app1/Botao` → (`app1`, `Botao`), when both ends match.

    Matches the longest prefix first, because the unit name may contain
    a slash — `@org/app1/Botao` is the unit `@org/app1` publishing
    `./Botao`.
    """

    parts = module.split("/")

    for cut in range(len(parts) - 1, 0, -1):

        candidate = "/".join(parts[:cut])
        rest = "/".join(parts[cut:])

        if rest in catalog.get(candidate, set()):
            return candidate, rest

    return None, ""
