"""Resolução de especificadores de módulo para arquivos."""

from __future__ import annotations

from pathlib import Path


class ModuleResolver:
    """
    Resolve `./fragments/X` para o arquivo real, seguindo as
    convenções do bundler: extensão implícita e `/index`.
    """

    EXTENSIONS = (".js", ".jsx", ".ts", ".tsx")

    @classmethod
    def resolve(cls, specifier: str, importer: Path) -> Path | None:

        if not specifier.startswith("."):
            return None

        base = (importer.parent / specifier).resolve()

        if base.is_file():
            return base

        for extension in cls.EXTENSIONS:

            candidate = base.with_suffix(extension)

            if candidate.is_file():
                return candidate

        for extension in cls.EXTENSIONS:

            candidate = base / f"index{extension}"

            if candidate.is_file():
                return candidate

        return None
