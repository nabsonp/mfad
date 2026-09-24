"""
Estado compartilhado de uma reconstrução.

O repositório é varrido UMA vez. Durante essa varredura são
colhidas, juntas, as duas coisas que o resto do processo
precisa: as constantes do repositório e os `registerApplication`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Node

from damfe.adapters.driven.reconstruction.ast import (
    AstReader,
    RouteConstantTable,
    SourceTree,
)
from damfe.adapters.driven.reconstruction.singlespa import sizing
from damfe.domain import CodeSize


@dataclass
class Registration:
    """
    Um `registerApplication` encontrado no orquestrador.

    É a fonte de verdade do single-spa sobre quais aplicações
    existem — inclusive as que não têm pacote próprio.
    """

    name: str
    active_when: list[str]
    specifier: str | None
    declared_in: Path


@dataclass
class ScanContext:

    repository: Path
    tree: SourceTree
    reader: AstReader
    routes: RouteConstantTable
    registrations: list[Registration] = field(default_factory=list)
    packages: dict[str, Path] = field(default_factory=dict)

    #: caminho -> (linhas físicas, linhas de código)
    measurements: dict[Path, tuple[int, int]] = field(default_factory=dict)

    @classmethod
    def build(cls, repository: Path) -> "ScanContext":

        tree = SourceTree(repository)

        context = cls(
            repository=repository,
            tree=tree,
            reader=AstReader(),
            routes=RouteConstantTable(),
        )

        context.packages = context._index_packages()

        context._scan()

        context.routes.resolve_pending()

        return context

    def relative(self, path: Path) -> str:
        return self.tree.relative(path)

    def size_of(self, directory: Path) -> "CodeSize":
        """Soma as medições dos arquivos sob um diretório."""

        return sizing.total(
            [
                measurement
                for path, measurement in self.measurements.items()
                if directory in path.parents
            ]
        )

    def package_dir(self, file_path: Path) -> Path:

        directory = file_path.parent

        while directory != self.repository:

            if (directory / "package.json").is_file():
                return directory

            directory = directory.parent

        return self.repository

    def _index_packages(self) -> dict[str, Path]:

        index: dict[str, Path] = {}

        for manifest_file in self.tree.manifests():

            try:
                manifest = json.loads(
                    manifest_file.read_text(encoding="utf-8")
                )
            except Exception:
                continue

            name = manifest.get("name")

            if name:
                index.setdefault(name, manifest_file.parent)

        return index

    def _scan(self) -> None:

        for file_path in self.tree.source_files():

            try:
                root, source = self.reader.parse(file_path)
            except Exception:
                continue

            self.routes.index_file(root, source)

            self.measurements[file_path] = sizing.measure(root, source)

            self.registrations.extend(
                self._registrations(root, source, file_path)
            )

    def _registrations(
        self,
        root: Node,
        source: bytes,
        file_path: Path,
    ) -> list[Registration]:

        found: list[Registration] = []

        for node in AstReader.find_all(root, "call_expression"):

            function = node.child_by_field_name("function")

            if not function:
                continue

            if AstReader.text(function, source) != "registerApplication":
                continue

            registration = self._registration(node, source, file_path)

            if registration:
                found.append(registration)

        return found

    def _registration(
        self,
        node: Node,
        source: bytes,
        file_path: Path,
    ) -> Registration | None:
        """
        Lê um `registerApplication` nas duas formas aceitas:

            registerApplication({ name, app, activeWhen })
            registerApplication(name, loadingFn, activeWhen)
        """

        arguments = node.child_by_field_name("arguments")

        if not arguments:
            return None

        parts = [
            child
            for child in arguments.named_children
            if child.type != "comment"
        ]

        if not parts:
            return None

        if parts[0].type == "object":
            name, active_when, loader = self._object_form(parts[0], source)
        else:
            name, active_when, loader = self._positional_form(parts, source)

        if not name:
            return None

        return Registration(
            name=name,
            active_when=active_when,
            specifier=(
                self._loader_specifier(loader, source) if loader else None
            ),
            declared_in=file_path,
        )

    def _object_form(
        self,
        node: Node,
        source: bytes,
    ) -> tuple[str | None, list[str], Node | None]:

        name: str | None = None
        active_when: list[str] = []
        loader: Node | None = None

        for pair in node.named_children:

            if pair.type != "pair":
                continue

            key_node = pair.child_by_field_name("key")
            value_node = pair.child_by_field_name("value")

            if not key_node or not value_node:
                continue

            key = AstReader.strip_quotes(AstReader.text(key_node, source))

            if key == "name":
                name = AstReader.strip_quotes(
                    AstReader.text(value_node, source)
                )

            elif key == "activeWhen":
                active_when = self._string_literals(value_node, source)

            elif key == "app":
                loader = value_node

        return name, active_when, loader

    def _positional_form(
        self,
        parts: list[Node],
        source: bytes,
    ) -> tuple[str | None, list[str], Node | None]:

        name = AstReader.strip_quotes(AstReader.text(parts[0], source))

        loader = parts[1] if len(parts) > 1 else None

        active_when = (
            self._string_literals(parts[2], source)
            if len(parts) > 2
            else []
        )

        return name, active_when, loader

    @staticmethod
    def _string_literals(node: Node, source: bytes) -> list[str]:

        return [
            AstReader.strip_quotes(AstReader.text(literal, source))
            for literal in AstReader.find_all(node, "string")
        ]

    @staticmethod
    def _loader_specifier(node: Node, source: bytes) -> str | None:
        """
        Extrai o módulo carregado pelo `app`:

            () => System.import("@org/mfe-users")
            () => import("./monolito")
            "@org/mfe-users"
        """

        if node.type in {"string", "template_string"}:
            return AstReader.strip_quotes(AstReader.text(node, source))

        for call in AstReader.find_all(node, "call_expression"):

            function = call.child_by_field_name("function")

            if not function:
                continue

            text = AstReader.text(function, source)

            if text != "import" and not text.endswith(".import"):
                continue

            arguments = call.child_by_field_name("arguments")

            if not arguments:
                continue

            for child in arguments.named_children:

                if child.type in {"string", "template_string"}:
                    return AstReader.strip_quotes(
                        AstReader.text(child, source)
                    )

        return None
