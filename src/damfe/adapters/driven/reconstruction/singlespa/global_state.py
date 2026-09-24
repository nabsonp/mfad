"""
Acesso ao estado global.

Dois micro frontends que leem a mesma fatia do estado estão
acoplados sem trocar mensagem e sem importar nada um do outro —
um acoplamento que nenhuma das outras extrações enxerga.

A detecção é por biblioteca conhecida, identificada pelo
especificador do import. Não há heurística de nome: o que vem de
`react-redux` é acesso a estado, chame-se a variável como se
chamar.

Só a LEITURA é extraída. `useSelector((state) => state.cart)`
percorre o caminho explicitamente, e é isso que se registra. A
escrita — `dispatch(addProduto(item))` — revela apenas o nome da
ação no ponto da chamada; saber que fatia ela altera exigiria
seguir o redutor, que pode nem estar no mesmo repositório.
"""

from __future__ import annotations

from pathlib import Path

from tree_sitter import Node

from damfe.adapters.driven.reconstruction.ast import AstReader, ImportTable
from damfe.adapters.driven.reconstruction.singlespa import libraries
from damfe.adapters.driven.reconstruction.singlespa.context import ScanContext
from damfe.adapters.driven.reconstruction.singlespa.ownership import Ownership
from damfe.domain import MicroFrontend, SourceLocation, StateAccess


class GlobalStateExtractor:

    def __init__(
        self,
        context: ScanContext,
        microfrontends: list[MicroFrontend],
    ):
        self.context = context

        self.ownership = Ownership(context.repository, microfrontends)

        self.known = {item.id for item in microfrontends}

    def extract(self) -> list[StateAccess]:

        found: list[StateAccess] = []

        for file_path in self.context.tree.source_files():

            try:
                root, source = self.context.reader.parse(file_path)
            except Exception:
                continue

            found.extend(self._from_file(file_path, root, source))

        return sorted(
            found,
            key=lambda item: (
                item.microfrontend,
                item.path,
                item.at.file,
                item.at.line,
            ),
        )

    def _from_file(
        self,
        file_path: Path,
        root: Node,
        source: bytes,
    ) -> list[StateAccess]:

        bindings = self._bindings(root, source)

        if not bindings:
            return []

        owner = self.ownership.of_file(file_path)

        # Acesso em pacote compartilhado não é acoplamento entre
        # micro frontends: não há de quem para quem.
        if owner not in self.known:
            return []

        relative = self.context.relative(file_path)

        found: list[StateAccess] = []

        for node in AstReader.find_all(root, "call_expression"):

            function = node.child_by_field_name("function")

            if not function or function.type != "identifier":
                continue

            entry = bindings.get(AstReader.text(function, source))

            if not entry:
                continue

            library, kind = entry

            for path in self._accesses(node, source, kind):

                found.append(
                    StateAccess(
                        microfrontend=owner,
                        library=library.name,
                        path=path,
                        at=SourceLocation(
                            file=relative,
                            line=node.start_point.row + 1,
                            code=self._line(node, source),
                        ),
                    )
                )

        return found

    # ------------------------------------------------------------------
    # Quem é o quê neste arquivo
    # ------------------------------------------------------------------

    @staticmethod
    def _bindings(
        root: Node,
        source: bytes,
    ) -> dict[str, tuple[libraries.StateLibrary, str]]:
        """Nome local -> (biblioteca, papel da função)."""

        by_module = {
            library.module: library
            for library in libraries.STATE_LIBRARIES
        }

        bindings: dict[str, tuple[libraries.StateLibrary, str]] = {}

        for record in ImportTable.records(root, source):

            library = by_module.get(record.module)

            if not library:
                continue

            for kind, names in (
                ("selector", library.selectors),
                ("atom", library.atoms),
            ):
                if record.imported_name in names:
                    bindings[record.local_name] = (library, kind)

        return bindings

    # ------------------------------------------------------------------
    # Leituras
    # ------------------------------------------------------------------

    def _accesses(
        self,
        node: Node,
        source: bytes,
        kind: str,
    ) -> list[str]:

        arguments = self._arguments(node)

        if not arguments:
            return []

        if kind == "atom":

            name = AstReader.text(arguments[0], source).strip()

            return [name] if name.isidentifier() else []

        if kind == "selector":
            return self._paths(arguments[0], source)

        return []

    def _paths(self, selector: Node, source: bytes) -> list[str]:
        """
        Os caminhos que um seletor percorre.

        `(state) => state.cart` devolve `cart`. Um seletor que monta
        objeto — `(state) => ({ user: state.user, cart: state.cart })` —
        devolve os dois: são duas fatias lidas, não uma.
        """

        parameter = self._first_parameter(selector, source)

        if not parameter:
            return []

        body = selector.child_by_field_name("body") or selector

        paths: list[str] = []

        for node in AstReader.find_all(body, "member_expression"):

            path = self._path_from(node, source, parameter)

            if path and path not in paths:
                paths.append(path)

        return paths

    @staticmethod
    def _first_parameter(selector: Node, source: bytes) -> str | None:

        if selector.type not in {
            "arrow_function",
            "function_expression",
            "function_declaration",
        }:
            return None

        parameter = selector.child_by_field_name("parameter")

        if parameter:
            return AstReader.text(parameter, source)

        parameters = selector.child_by_field_name("parameters")

        if not parameters:
            return None

        for child in parameters.named_children:

            if child.type == "identifier":
                return AstReader.text(child, source)

        return None

    @staticmethod
    def _path_from(
        node: Node,
        source: bytes,
        parameter: str,
    ) -> str | None:
        """
        `state.user.profile` vira `user.profile`.

        Só a expressão mais externa interessa: as internas são
        prefixos dela e contariam a mesma leitura duas vezes.
        """

        if node.parent and node.parent.type == "member_expression":
            return None

        text = AstReader.text(node, source)

        head, _, rest = text.partition(".")

        if head.strip() != parameter or not rest:
            return None

        return rest.strip()

    # ------------------------------------------------------------------

    @staticmethod
    def _arguments(node: Node) -> list[Node]:

        arguments = node.child_by_field_name("arguments")

        if not arguments:
            return []

        return [
            child
            for child in arguments.named_children
            if child.type != "comment"
        ]

    @staticmethod
    def _line(node: Node, source: bytes) -> str:

        return " ".join(AstReader.text(node, source).split())[:160]
