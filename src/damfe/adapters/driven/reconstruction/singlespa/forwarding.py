"""
Funções do projeto que repassam um parâmetro a uma API conhecida.

Projetos embrulham a API da plataforma numa função própria — o
`fetchApi(url)` que chama `fetch`, o `setItem(key, value)` que grava
no `localStorage` — e o valor que importa só aparece em quem chama a
embrulhadora. O critério é fluxo de dado, não nome: a função que
repassa um parâmetro seu à API vira embrulhadora, e quem repassa o
próprio parâmetro a uma embrulhadora também, em camadas.

Este módulo guarda o que as extrações têm em comum: reconhecer o
parâmetro e iterar as camadas até nada novo aparecer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from tree_sitter import Node

from damfe.adapters.driven.reconstruction.ast import AstReader
from damfe.adapters.driven.reconstruction.ast.symbols import (
    FUNCTION_TYPES,
    ModuleSymbols,
    parameters,
)


#: Quantas camadas de função embrulhando outra se seguem.
MAX_LAYERS = 5


@dataclass(frozen=True)
class Parameter:
    """Valor que é parâmetro da função em volta."""

    function: Node
    index: int


def parameter_of(identifier: Node, symbols: ModuleSymbols) -> Parameter | None:
    """O parâmetro de função que o nome designa, se for um."""

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
    Aplica `step` a toda chamada, rodada após rodada.

    `step` diz se achou embrulhadora nova. A primeira rodada acha as
    que chamam a API direto; cada rodada seguinte, as que chamam uma
    da anterior. Para quando uma rodada não acha nada.
    """

    calls = {
        symbols.path: list(AstReader.find_all(symbols.root, "call_expression"))
        for symbols in files
    }

    for _ in range(MAX_LAYERS):

        # Sem curto-circuito: todas as chamadas da rodada contam.
        found = [step(node, symbols) for symbols in files for node in calls[symbols.path]]

        if not any(found):
            return
