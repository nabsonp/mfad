"""Varredura de arquivos-fonte com poda de diretórios."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from damfe.adapters.driven.reconstruction.ast.reader import AstReader


class SourceTree:
    """
    Percorre os arquivos-fonte de um repositório.

    A poda acontece na descida — diretórios ignorados nunca
    são abertos. Isso importa: `rglob` desce em `node_modules`
    inteiro antes de descartar, e a diferença é de minutos
    para segundos num repositório real.
    """

    IGNORED_DIRECTORIES = {
        "node_modules",
        "dist",
        "build",
        ".git",
        ".next",
        "coverage",
        "__pycache__",
    }

    def __init__(self, root: Path):
        self.root = root

    def source_files(self) -> Iterator[Path]:

        for path in self._walk():

            if path.suffix in AstReader.SUPPORTED_EXTENSIONS:
                yield path

    def markup_files(self) -> Iterator[Path]:
        """HTML e templates, onde mora o layout declarativo."""

        for path in self._walk():

            if path.suffix in (".html", ".ejs", ".htm"):
                yield path

    def manifests(self, name: str = "package.json") -> Iterator[Path]:

        for path in self._walk():

            if path.name == name:
                yield path

    def _walk(self) -> Iterator[Path]:

        stack = [self.root]

        while stack:

            directory = stack.pop()

            try:
                entries = list(directory.iterdir())
            except OSError:
                continue

            for path in entries:

                if path.is_dir():

                    if path.name in self.IGNORED_DIRECTORIES:
                        continue

                    stack.append(path)

                else:
                    yield path

    def relative(self, path: Path) -> str:

        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)
