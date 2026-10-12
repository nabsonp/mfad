"""
Se o código de uma ponta de canal pode chegar a executar.

`dispatchEvent` dentro de uma função que ninguém chama não comunica
nada, mas estar no arquivo do micro frontend bastava para virar
aresta. O critério é o de "símbolo sem uso" dos compiladores e
linters, restrito ao que se decide sem executar:

- função NÃO exportada sem nenhuma referência no próprio arquivo é
  morta;
- função EXPORTADA é morta quando o arquivo dela é importado por
  outros do projeto e nenhum desses imports traz o nome — nem por
  namespace, nem por `export *`, nem por `import()`/`require`, que
  podem ler qualquer nome.

Arquivo que ninguém do projeto importa fica de fora da segunda regra:
pode ser entrada da aplicação, módulo exposto ao hospedeiro ou
arquivo carregado pelo framework, e o consumidor não está no código
lido. Método de classe também fica de fora: o framework chama
`ngOnInit`, o template chama o tratador, e nada disso é import.
"""

from __future__ import annotations

from pathlib import Path

from tree_sitter import Node

from damfe.adapters.driven.reconstruction.ast import AstReader, ModuleResolver
from damfe.adapters.driven.reconstruction.ast.resolver import canonical
from damfe.adapters.driven.reconstruction.ast.symbols import (
    FUNCTION_TYPES,
    ModuleSymbols,
)
from damfe.adapters.driven.reconstruction.singlespa.context import ScanContext


#: Nome importado que pode ser qualquer um.
ANY = "*"


class Liveness:

    def __init__(self, context: ScanContext):

        self.context = context

        self.index = context.symbols()

        #: arquivo → nomes que algum outro arquivo importa dele
        self._imported: dict[Path, set[str]] | None = None

        self._references: dict[tuple[Path, str], bool] = {}

    def is_live(self, node: Node, symbols: ModuleSymbols) -> bool:
        """Se nenhuma função com nome em volta do nó está sem uso."""

        current = node.parent

        while current is not None:

            if current.type in FUNCTION_TYPES:

                key = self.index.key_of(current, symbols)

                if key and "." not in key and not self._used(symbols, key):
                    return False

            current = current.parent

        return True

    def _used(self, symbols: ModuleSymbols, name: str) -> bool:

        cache = (symbols.path, name)

        if cache not in self._references:
            self._references[cache] = self._referenced_here(symbols, name) or self._imported_elsewhere(
                symbols, name
            )

        return self._references[cache]

    @staticmethod
    def _referenced_here(symbols: ModuleSymbols, name: str) -> bool:
        """Algum uso do nome no arquivo além da própria declaração."""

        for node in AstReader.walk(symbols.root):

            if node.type not in ("identifier", "shorthand_property_identifier"):
                continue

            if symbols.text(node) != name:
                continue

            parent = node.parent

            if parent is None:
                continue

            # A declaração não é uso, e `export { f }` só torna o nome
            # visível — quem usa é o importador.
            if parent.type in ("function_declaration", "generator_function_declaration", "variable_declarator"):

                if parent.child_by_field_name("name") == node:
                    continue

            if parent.type == "export_specifier":
                continue

            return True

        return False

    def _imported_elsewhere(self, symbols: ModuleSymbols, name: str) -> bool:

        exported = [alias for alias, local in symbols.exports.items() if local == name]

        if not exported:
            return False

        # Exportada como padrão: o nome com que se importa é qualquer um.
        if "default" in exported:
            return True

        imported = self._imports().get(symbols.path)

        # Ninguém do projeto importa o arquivo: o consumidor não está
        # no código lido.
        if imported is None:
            return True

        return ANY in imported or any(alias in imported for alias in exported)

    def _imports(self) -> dict[Path, set[str]]:
        """Para cada arquivo do projeto, os nomes que outros importam dele."""

        if self._imported is not None:
            return self._imported

        found: dict[Path, set[str]] = {}

        for file_path in self.context.tree.source_files():

            symbols = self.index.of(file_path)

            if symbols is None:
                continue

            for local, (module, imported) in symbols.imports.items():

                target = ModuleResolver.resolve(module, symbols.path)

                if target is not None:
                    found.setdefault(canonical(target), set()).add(imported)

            for module, names in self._other_imports(symbols):

                target = ModuleResolver.resolve(module, symbols.path)

                if target is not None:
                    found.setdefault(canonical(target), set()).update(names)

        self._imported = found

        return found

    @staticmethod
    def _other_imports(symbols: ModuleSymbols) -> list[tuple[str, set[str]]]:
        """`export … from`, `import()` e `require()`."""

        found: list[tuple[str, set[str]]] = []

        for node in AstReader.walk(symbols.root):

            if node.type == "export_statement":

                origin = node.child_by_field_name("source")

                if origin is None:
                    continue

                clause = [child for child in node.named_children if child.type == "export_clause"]

                names = (
                    {
                        symbols.text(name)
                        for specifier in clause[0].named_children
                        if specifier.type == "export_specifier"
                        and (name := specifier.child_by_field_name("name")) is not None
                    }
                    if clause
                    else {ANY}
                )

                found.append((AstReader.strip_quotes(symbols.text(origin)), names))

            elif node.type == "call_expression":

                function = node.child_by_field_name("function")
                arguments = node.child_by_field_name("arguments")

                if function is None or arguments is None:
                    continue

                if function.type != "import" and symbols.text(function) != "require":
                    continue

                strings = [child for child in arguments.named_children if child.type == "string"]

                if strings:
                    found.append((AstReader.strip_quotes(symbols.text(strings[0])), {ANY}))

        return found
