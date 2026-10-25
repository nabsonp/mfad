"""
Avaliação parcial de expressões.

Resolve estaticamente o quanto der de uma expressão que produz uma
URL. Cada forma reconhecida tem uma regra; o que não casa com
nenhuma fica sem resolver, e isso é resposta legítima — a
alternativa seria adivinhar.

`exact` significa que a URL inteira foi determinada. `prefix`
significa que só o começo dela é estático, porque o resto depende
de valor de runtime.

`based` diz que a URL começa depois de uma base desconhecida:
`${API_URL}/users` vale `/users`. Chamada a serviço quase sempre é
escrita assim — a base vem de variável de ambiente —, e descartar a
expressão inteira deixava o sistema sem chamada externa nenhuma.
Quem usa decide se a base importa: o caminho de um serviço não
depende dela, a navegação depende.
"""

from __future__ import annotations

from dataclasses import dataclass

from tree_sitter import Node

from mfad.adapters.driven.reconstruction.ast import (
    AstReader,
    RouteConstantTable,
)


EXACT = "exact"
PREFIX = "prefix"

#: Trecho de runtime dentro de uma URL.
PARAM = "{param}"


@dataclass
class Value:
    url: str
    match: str

    #: a URL vem depois de uma base que não se resolve
    based: bool = False

    #: a URL inteira, com `{param}` em cada trecho de runtime, quando
    #: ela tem mais texto depois do prefixo: `/movie/{param}`
    pattern: str | None = None


class ExpressionEvaluator:

    def __init__(self, constants: RouteConstantTable):
        self.constants = constants

    def evaluate(self, node: Node, source: bytes) -> Value | None:

        if node.type == "string":
            return Value(
                AstReader.strip_quotes(AstReader.text(node, source)),
                EXACT,
            )

        if node.type == "identifier":

            url = self.constants.resolve(AstReader.text(node, source))

            return Value(url, EXACT) if url else None

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

        head, marker, rest = inner.partition("${")

        if head:
            return Value(head, PREFIX if marker else EXACT, pattern=self._pattern(node, source) if marker else None)

        if not marker:
            return None

        # `${base}/users/${id}`: a base é desconhecida, o caminho
        # depois dela não. Só vale quando o que segue é caminho — o
        # texto logo após a substituição começa com "/".
        _, closed, after = rest.partition("}")

        if not closed or not after.startswith("/"):
            return None

        path, marker, _ = after.partition("${")

        return Value(path, PREFIX if marker else EXACT, based=True)

    @staticmethod
    def _pattern(node: Node, source: bytes) -> str:
        """O texto do template com `{param}` no lugar de cada substituição."""

        parts: list[str] = []

        position = node.start_byte + 1

        for child in node.named_children:

            if child.type != "template_substitution":
                continue

            parts.append(source[position:child.start_byte].decode("utf-8", "replace"))
            parts.append(PARAM)

            position = child.end_byte

        parts.append(source[position:node.end_byte - 1].decode("utf-8", "replace"))

        return "".join(parts)

    def _concatenation(self, node: Node, source: bytes) -> Value | None:

        operator = node.child_by_field_name("operator")

        if not operator or AstReader.text(operator, source) != "+":
            return None

        left = node.child_by_field_name("left")

        if not left:
            return None

        value = self.evaluate(left, source)

        if value:
            return Value(value.url, PREFIX, value.based)

        # `API_URL + "/users"`: base desconhecida, caminho literal.
        right = node.child_by_field_name("right")

        if left.type in ("identifier", "member_expression") and right is not None:

            tail = self.evaluate(right, source)

            if tail and tail.url.startswith("/") and not tail.based:
                return Value(tail.url, tail.match, based=True)

        return None

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
