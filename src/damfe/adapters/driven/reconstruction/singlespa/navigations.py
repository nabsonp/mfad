"""
Navegação entre aplicações.

Não existe API padrão de navegação no single-spa: cada projeto usa
o roteador do seu framework, ou um componente próprio. Detectar a
CHAMADA, portanto, não é genérico.

O destino é. Toda aplicação declara no `registerApplication` as
rotas que possui, e isso vale para qualquer projeto single-spa.
Por isso a detecção é invertida: em vez de procurar chamadas de
navegação e descobrir para onde vão, procuramos expressões que
resolvem para uma rota de OUTRA aplicação. O que aciona a
navegação deixa de importar.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from tree_sitter import Node

from damfe.adapters.driven.reconstruction.ast import AstReader
from damfe.adapters.driven.reconstruction.singlespa.context import ScanContext
from damfe.adapters.driven.reconstruction.singlespa.expressions import (
    ExpressionEvaluator,
)
from damfe.adapters.driven.reconstruction.singlespa.ownership import Ownership
from damfe.domain import MicroFrontend, Navigation, SourceLocation


class NavigationExtractor:

    def __init__(
        self,
        context: ScanContext,
        microfrontends: list[MicroFrontend],
    ):
        self.context = context

        self.ownership = Ownership(context.repository, microfrontends)

        self.evaluator = ExpressionEvaluator(context.routes)

    def extract(self) -> list[Navigation]:

        found: list[Navigation] = []

        for file_path in self.context.tree.source_files():

            try:
                root, source = self.context.reader.parse(file_path)
            except Exception:
                continue

            found.extend(self._from_file(file_path, root, source))

        return sorted(
            found,
            key=lambda item: (
                item.source,
                item.target,
                item.at.file,
                item.at.line,
            ),
        )

    def _from_file(
        self,
        file_path: Path,
        root: Node,
        source: bytes,
    ) -> list[Navigation]:

        origin = self.ownership.of_file(file_path)

        relative = self.context.relative(file_path)

        found: list[Navigation] = []

        for node in self._candidates(root):

            value = self.evaluator.evaluate(node, source)

            if not value or not value.url.startswith("/"):
                continue

            target = self.ownership.of_route(value.url)

            if not target or target == origin:
                continue

            found.append(
                Navigation(
                    source=origin,
                    target=target,
                    expression=AstReader.text(node, source),
                    resolved_url=value.url,
                    match=value.match,
                    at=SourceLocation(
                        file=relative,
                        line=node.start_point.row + 1,
                        code=self._statement(node, source),
                    ),
                )
            )

        return found

    @staticmethod
    def _candidates(root: Node) -> Iterator[Node]:
        """
        As posições em que uma URL vira navegação.

        Argumento DIRETO de chamada cobre `navigate(rota)`; valor de
        atributo JSX cobre `<Link to={rota}>` e qualquer componente
        próprio que receba a rota por prop.

        Só o argumento direto, nunca aninhado: é o que mantém o
        `activeWhen: ["/users"]` do próprio `registerApplication`
        fora do resultado.
        """

        for node in AstReader.walk(root):

            if node.type == "call_expression":

                arguments = node.child_by_field_name("arguments")

                if not arguments:
                    continue

                for child in arguments.named_children:

                    if child.type != "comment":
                        yield child

            elif node.type == "jsx_attribute":

                parts = node.named_children

                if len(parts) < 2:
                    continue

                value = parts[1]

                if value.type != "jsx_expression":
                    yield value
                    continue

                for child in value.named_children:

                    if child.type != "comment":
                        yield child

    @staticmethod
    def _statement(node: Node, source: bytes) -> str:
        """O trecho de código em volta, para leitura humana."""

        current = node

        while current.parent and current.type not in {
            "expression_statement",
            "jsx_attribute",
            "jsx_self_closing_element",
            "return_statement",
        }:
            current = current.parent

        text = AstReader.text(current, source)

        return " ".join(text.split())[:160]
