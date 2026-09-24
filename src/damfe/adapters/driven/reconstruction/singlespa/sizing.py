"""
Medição de tamanho do código.

A contagem é feita durante a varredura que já acontece, sobre os
bytes que já foram lidos e a árvore que já foi construída — não
há segunda leitura do disco.

Linha de comentário é identificada pela árvore sintática, e não
por prefixo de texto: `//` dentro de uma string não conta como
comentário, e bloco `/* */` é reconhecido inteiro.
"""

from __future__ import annotations

from tree_sitter import Node

from damfe.adapters.driven.reconstruction.ast import AstReader
from damfe.domain import CodeSize


def measure(root: Node, source: bytes) -> tuple[int, int]:
    """Devolve `(linhas físicas, linhas de código)` de um arquivo."""

    text = source.decode("utf-8", errors="replace")

    lines = text.splitlines()

    if not lines:
        return 0, 0

    commented = _comment_only_rows(root, lines)

    code = sum(
        1
        for index, line in enumerate(lines)
        if line.strip() and index not in commented
    )

    return len(lines), code


def _comment_only_rows(root: Node, lines: list[str]) -> set[int]:
    """
    Linhas cujo conteúdo é apenas comentário.

    Uma linha com código e comentário ao final continua sendo
    linha de código — só entra aqui quando nada sobra fora do
    comentário.
    """

    rows: set[int] = set()

    for node in AstReader.find_all(root, "comment"):

        first, last = node.start_point.row, node.end_point.row

        for row in range(first, last + 1):

            if row >= len(lines):
                continue

            line = lines[row]

            before = (
                line[: node.start_point.column] if row == first else ""
            )
            after = line[node.end_point.column:] if row == last else ""

            if not before.strip() and not after.strip():
                rows.add(row)

    return rows


def total(measurements: list[tuple[int, int]]) -> CodeSize:

    return CodeSize(
        files=len(measurements),
        lines=sum(item[0] for item in measurements),
        code_lines=sum(item[1] for item in measurements),
    )
