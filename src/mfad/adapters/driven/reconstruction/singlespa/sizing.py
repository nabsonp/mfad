"""
Measurement of code size.

Counting is done during the scan that already happens, over the bytes
already read and the tree already built — there is no second read
from disk.

A comment line is identified by the syntax tree, not by a text
prefix: `//` inside a string does not count as a comment, and a
`/* */` block is recognized as a whole.
"""

from __future__ import annotations

from tree_sitter import Node

from mfad.adapters.driven.reconstruction.ast import AstReader
from mfad.domain import CodeSize


def measure(root: Node, source: bytes) -> tuple[int, int]:
    """Returns `(physical lines, lines of code)` of a file."""

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
    Lines whose content is only a comment.

    A line with code and a trailing comment is still a line of code —
    it only counts here when nothing is left outside the comment.
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
