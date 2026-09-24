"""
Avaliação parcial de expressões.

Resolve estaticamente o quanto der de uma expressão que produz uma
URL. Cada forma reconhecida tem uma regra; o que não casa com
nenhuma fica sem resolver, e isso é resposta legítima — a
alternativa seria adivinhar.

`exact` significa que a URL inteira foi determinada. `prefix`
significa que só o começo dela é estático, porque o resto depende
de valor de runtime.
"""

from __future__ import annotations

from dataclasses import dataclass

from tree_sitter import Node

from damfe.adapters.driven.reconstruction.ast import (
    AstReader,
    RouteConstantTable,
)


EXACT = "exact"
PREFIX = "prefix"


@dataclass
class Value:
    url: str
    match: str


class ExpressionEvaluator:

    def __init__(self, constants: RouteConstantTable):
        self.constants = constants

    def evaluate(self, node: Node, source: bytes) -> Value | None:

        if node.type == "string":
            return Value(
                AstReader.strip_quotes(AstReader.text(node, source)),
                EXACT,
            )

        if node.type == "member_expression":

            url = self.constants.resolve(AstReader.text(node, source))

            return Value(url, EXACT) if url else None

        if node.type == "template_string":
            return self._template(node, source)

        if node.type == "binary_expression":
            return self._concatenation(node, source)

        if node.type == "call_expression":
            return self._replace(node, source)

        return None

    def _template(self, node: Node, source: bytes) -> Value | None:
        """
        `/products/${id}` vale o prefixo `/products/`.

        Serve porque o `activeWhen` também é prefixo: o que vem
        antes da primeira substituição já basta para saber de quem
        é a rota.
        """

        text = AstReader.text(node, source)

        inner = text[1:-1] if len(text) >= 2 else ""

        head, marker, _ = inner.partition("${")

        if not head:
            return None

        return Value(head, PREFIX if marker else EXACT)

    def _concatenation(self, node: Node, source: bytes) -> Value | None:

        operator = node.child_by_field_name("operator")

        if not operator or AstReader.text(operator, source) != "+":
            return None

        left = node.child_by_field_name("left")

        if not left:
            return None

        value = self.evaluate(left, source)

        return Value(value.url, PREFIX) if value else None

    def _replace(self, node: Node, source: bytes) -> Value | None:
        """
        `routes.COMPRA.replace(":id", id)` vale o trecho anterior ao
        parâmetro: `/checkout/purchases/`.
        """

        function = node.child_by_field_name("function")

        if not function or function.type != "member_expression":
            return None

        method = function.child_by_field_name("property")

        if not method or AstReader.text(method, source) != "replace":
            return None

        receiver = function.child_by_field_name("object")

        if not receiver:
            return None

        value = self.evaluate(receiver, source)

        if not value:
            return None

        arguments = node.child_by_field_name("arguments")

        if not arguments:
            return None

        needles = [
            child
            for child in arguments.named_children
            if child.type == "string"
        ]

        if not needles:
            return None

        needle = AstReader.strip_quotes(AstReader.text(needles[0], source))

        head, marker, _ = value.url.partition(needle)

        if not head:
            return None

        return Value(head, PREFIX if marker else value.match)
