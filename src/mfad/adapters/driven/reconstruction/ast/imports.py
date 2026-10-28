"""Import table of a file."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from tree_sitter import Node

from mfad.adapters.driven.reconstruction.ast.reader import AstReader
from mfad.adapters.driven.reconstruction.ast.resolver import ModuleResolver


@dataclass
class ImportRecord:
    """A name brought in by an import, with its origin."""

    local_name: str
    imported_name: str
    module: str
    line: int
    code: str


class ImportTable:
    """Map 'local name' -> 'module specifier'."""

    def __init__(self, root: Node, source: bytes, file_path: Path):

        self.file_path = file_path

        self.bindings: dict[str, str] = {}

        for record in self.records(root, source):
            self.bindings[record.local_name] = record.module

    @classmethod
    def records(
        cls,
        root: Node,
        source: bytes,
    ) -> Iterator[ImportRecord]:
        """Walks each imported name, default or named."""

        for node in AstReader.find_all(root, "import_statement"):

            source_node = node.child_by_field_name("source")

            if not source_node:
                continue

            module = AstReader.strip_quotes(
                AstReader.text(source_node, source)
            )

            code = AstReader.text(node, source)
            line = node.start_point.row + 1

            for clause in node.children:

                if clause.type != "import_clause":
                    continue

                for child in clause.named_children:

                    # import App from "./App"
                    if child.type == "identifier":

                        name = AstReader.text(child, source)

                        yield ImportRecord(
                            local_name=name,
                            imported_name="default",
                            module=module,
                            line=line,
                            code=code,
                        )

                    # import * as api from "./x"
                    elif child.type == "namespace_import":

                        names = [
                            item for item in child.named_children
                            if item.type == "identifier"
                        ]

                        if names:
                            yield ImportRecord(
                                local_name=AstReader.text(names[0], source),
                                imported_name="*",
                                module=module,
                                line=line,
                                code=code,
                            )

                    # import { a, b as c } from "./x"
                    elif child.type == "named_imports":

                        for specifier in child.named_children:

                            if specifier.type != "import_specifier":
                                continue

                            name_node = specifier.child_by_field_name(
                                "name"
                            )

                            if not name_node:
                                continue

                            alias_node = specifier.child_by_field_name(
                                "alias"
                            )

                            imported = AstReader.text(name_node, source)

                            local = (
                                AstReader.text(alias_node, source)
                                if alias_node
                                else imported
                            )

                            yield ImportRecord(
                                local_name=local,
                                imported_name=imported,
                                module=module,
                                line=line,
                                code=code,
                            )

    def file_for(self, local_name: str) -> Path | None:

        specifier = self.bindings.get(local_name)

        if not specifier:
            return None

        return ModuleResolver.resolve(specifier, self.file_path)
