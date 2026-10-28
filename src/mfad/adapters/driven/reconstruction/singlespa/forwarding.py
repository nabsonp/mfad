"""
Project functions that forward a parameter to a known API.

Projects wrap the platform API in a function of their own — the
`fetchApi(url)` that calls `fetch`, the `setItem(key, value)` that
writes to `localStorage` — and the value that matters only appears in
whoever calls the wrapper. The criterion is data flow, not name: the
function that forwards one of its parameters to the API becomes a
wrapper, and so does whoever forwards its own parameter to a wrapper,
in layers.

This module holds what the extractions have in common: recognizing the
parameter and iterating over the layers until nothing new shows up.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from tree_sitter import Node

from mfad.adapters.driven.reconstruction.ast import AstReader
from mfad.adapters.driven.reconstruction.ast.symbols import (
    FUNCTION_TYPES,
    ModuleSymbols,
    parameters,
)


#: How many layers of a function wrapping another are followed.
MAX_LAYERS = 5


@dataclass(frozen=True)
class Parameter:
    """Value that is a parameter of the enclosing function."""

    function: Node
    index: int


def parameter_of(identifier: Node, symbols: ModuleSymbols) -> Parameter | None:
    """The function parameter the name designates, if it is one."""

    name = symbols.text(identifier)

    current = identifier.parent

    while current is not None:

        if current.type in FUNCTION_TYPES:

            names = parameters(current, symbols.source)

            if name in names:
                return Parameter(function=current, index=names.index(name))

        current = current.parent

    return None


def until_stable(
    files: list[ModuleSymbols],
    step: Callable[[Node, ModuleSymbols], bool],
) -> None:
    """
    Applies `step` to every call, round after round.

    `step` says whether it found a new wrapper. The first round finds
    the ones that call the API directly; each following round, the ones
    that call one from the previous round. Stops when a round finds
    nothing.
    """

    calls = {
        symbols.path: list(AstReader.find_all(symbols.root, "call_expression"))
        for symbols in files
    }

    for _ in range(MAX_LAYERS):

        # No short-circuit: every call in the round counts.
        found = [step(node, symbols) for symbols in files for node in calls[symbols.path]]

        if not any(found):
            return
