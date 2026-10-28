"""
Partial evaluation of expressions.

Statically resolves as much as possible of an expression that produces
a URL. Each recognized form has a rule; what matches none stays
unresolved, and that is a legitimate answer — the alternative would be
guessing.

`exact` means the whole URL was determined. `prefix` means only its
beginning is static, because the rest depends on a runtime value.

`based` says the URL starts after an unknown base: `${API_URL}/users`
evaluates to `/users`. Service calls are almost always written like
this — the base comes from an environment variable —, and discarding
the whole expression left the system with no external calls at all.
The caller decides whether the base matters: a service's path does not
depend on it, navigation does.
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

#: Runtime segment inside a URL.
PARAM = "{param}"


@dataclass
class Value:
    url: str
    match: str

    #: the URL comes after a base that does not resolve
    based: bool = False

    #: the whole URL, with `{param}` in each runtime segment, when it
    #: has more text after the prefix: `/movie/{param}`
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
        `/products/${id}` evaluates to the prefix `/products/`.

        This works because `activeWhen` is also a prefix: what comes
        before the first substitution is already enough to know whose
        route it is.
        """

        text = AstReader.text(node, source)

        inner = text[1:-1] if len(text) >= 2 else ""

        head, marker, rest = inner.partition("${")

        if head:
            return Value(head, PREFIX if marker else EXACT, pattern=self._pattern(node, source) if marker else None)

        if not marker:
            return None

        # `${base}/users/${id}`: the base is unknown, the path after it
        # is not. Only valid when what follows is a path — the text
        # right after the substitution starts with "/".
        _, closed, after = rest.partition("}")

        if not closed or not after.startswith("/"):
            return None

        path, marker, _ = after.partition("${")

        return Value(path, PREFIX if marker else EXACT, based=True)

    @staticmethod
    def _pattern(node: Node, source: bytes) -> str:
        """The template text with `{param}` in place of each substitution."""

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

        # `API_URL + "/users"`: unknown base, literal path.
        right = node.child_by_field_name("right")

        if left.type in ("identifier", "member_expression") and right is not None:

            tail = self.evaluate(right, source)

            if tail and tail.url.startswith("/") and not tail.based:
                return Value(tail.url, tail.match, based=True)

        return None

    def _replace(self, node: Node, source: bytes) -> Value | None:
        """
        `routes.COMPRA.replace(":id", id)` evaluates to the segment
        before the parameter: `/checkout/purchases/`.
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
