"""Thin layer over Tree-sitter, framework-independent."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import tree_sitter_javascript as ts_javascript
import tree_sitter_typescript as ts_typescript
from tree_sitter import Language, Node, Parser


JS_LANGUAGE = Language(ts_javascript.language())
TS_LANGUAGE = Language(ts_typescript.language_typescript())
TSX_LANGUAGE = Language(ts_typescript.language_tsx())


class AstReader:
    """Picks the parser by extension and navigates the tree."""

    SUPPORTED_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx"}

    def __init__(self):

        # Trees must be kept alive: a tree-sitter `Node` points to
        # memory owned by the `Tree`, and if the tree is garbage
        # collected the node becomes a dangling pointer — the process
        # dies with a segmentation fault, with no exception.
        #
        # Keeping them by path also avoids re-parsing the same
        # file at every reconstruction step.
        self._trees: dict[Path, object] = {}

        self._parsers = {
            ".js": Parser(JS_LANGUAGE),
            ".jsx": Parser(JS_LANGUAGE),
            ".ts": Parser(TS_LANGUAGE),
            ".tsx": Parser(TSX_LANGUAGE),
        }

    def parse(self, file_path: Path) -> tuple[Node, bytes]:

        cached = self._trees.get(file_path)

        if cached:
            return cached[0].root_node, cached[1]

        parser = self._parsers.get(file_path.suffix)

        if not parser:
            raise ValueError(
                f"Unsupported extension: {file_path.suffix}"
            )

        source = file_path.read_bytes()

        tree = parser.parse(source)

        self._trees[file_path] = (tree, source)

        return tree.root_node, source

    @staticmethod
    def text(node: Node, source: bytes) -> str:

        return source[node.start_byte:node.end_byte].decode(
            "utf-8",
            errors="replace",
        )

    @classmethod
    def walk(cls, node: Node) -> Iterator[Node]:
        """
        Walks the tree depth-first, from left to
        right.

        Iterative, not recursive: `yield from` would stack one
        frame per AST level, and a tree of nested JSX
        exhausts the stack — the process dies with a segmentation
        fault, with no exception that can be caught.
        """

        stack = [node]

        while stack:

            current = stack.pop()

            yield current

            stack.extend(reversed(current.children))

    @classmethod
    def find_all(cls, node: Node, node_type: str) -> Iterator[Node]:

        for candidate in cls.walk(node):

            if candidate.type == node_type:
                yield candidate

    @staticmethod
    def strip_quotes(text: str) -> str:

        text = text.strip()

        if (
            len(text) >= 2
            and text[0] in "\"'`"
            and text[-1] in "\"'`"
        ):
            return text[1:-1]

        return text
