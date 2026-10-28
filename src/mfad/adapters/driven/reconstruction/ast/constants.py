"""
Constant propagation.

Recognizes object literals such as:

    const checkoutRoutes = {
        CART: "/checkout/cart",
    };

so that `path={checkoutRoutes.CART}` can be resolved.

Known limitations, relevant for interpreting the tool's
coverage:

1. The table is indexed by identifier name, globally.
   Two files with a different `const routes` collide.
2. Only the forms `const X = {...}` and `const X = "literal"` are
   recognized.
3. Transitive resolution has an iteration cap.

The simple constant — `const CART_KEY = "cart"` — follows the same
name-based indexing, with one extra safeguard: a name declared with
different values in different places does not resolve. That is what
makes it safe to also resolve a constant imported from another module
without following the import: if the name has only one value in the
repository, that is the one.
"""

from __future__ import annotations

from tree_sitter import Node

from mfad.adapters.driven.reconstruction.ast.reader import AstReader


class RouteConstantTable:
    """Table of the repository's string constants."""

    MAX_PASSES = 10

    def __init__(self):
        self.table: dict[str, dict[str, str]] = {}

        # entries whose value is another reference, e.g.:
        # routes.CART = checkoutRoutes.CART
        self.pending: dict[tuple[str, str], str] = {}

        #: `const X = "literal"` — name → values seen
        self.scalars: dict[str, set[str]] = {}

    def index_file(self, root: Node, source: bytes) -> None:

        for node in AstReader.find_all(root, "variable_declarator"):

            name_node = node.child_by_field_name("name")
            value_node = node.child_by_field_name("value")

            if not name_node or not value_node:
                continue

            if name_node.type != "identifier":
                continue

            # `{ ... } as const` and `{ ... } satisfies T`: the TypeScript
            # annotation wraps the literal, which is still the value.
            while value_node.type in ("as_expression", "satisfies_expression") and value_node.named_children:
                value_node = value_node.named_children[0]

            if value_node.type == "string" and self._is_const(node):
                self.scalars.setdefault(AstReader.text(name_node, source), set()).add(
                    AstReader.strip_quotes(AstReader.text(value_node, source))
                )
                continue

            if value_node.type != "object":
                continue

            holder = AstReader.text(name_node, source)

            self._index_object(holder, value_node, source)

    @staticmethod
    def _is_const(declarator: Node) -> bool:
        """Only `const`: `let` and `var` can be reassigned."""

        declaration = declarator.parent

        return (
            declaration is not None
            and declaration.type == "lexical_declaration"
            and declaration.child(0) is not None
            and declaration.child(0).type == "const"
        )

    def _index_object(
        self,
        holder: str,
        node: Node,
        source: bytes,
    ) -> None:

        for pair in node.named_children:

            if pair.type != "pair":
                continue

            key_node = pair.child_by_field_name("key")
            value_node = pair.child_by_field_name("value")

            if not key_node or not value_node:
                continue

            key = AstReader.strip_quotes(
                AstReader.text(key_node, source)
            )

            if value_node.type in {"string", "template_string"}:

                self.table.setdefault(holder, {})[key] = (
                    AstReader.strip_quotes(
                        AstReader.text(value_node, source)
                    )
                )

            elif value_node.type == "member_expression":

                self.pending[(holder, key)] = AstReader.text(
                    value_node,
                    source,
                )

    def resolve_pending(self) -> None:
        """
        Resolves references between constants, iterating until a
        fixed point. This is what makes `routes.CART = checkoutRoutes.CART`
        reach `/checkout/cart`.
        """

        for _ in range(self.MAX_PASSES):

            progressed = False

            for (holder, key), expression in list(self.pending.items()):

                value = self.resolve(expression)

                if value is None:
                    continue

                self.table.setdefault(holder, {})[key] = value

                del self.pending[(holder, key)]

                progressed = True

            if not progressed:
                break

    def resolve(self, expression: str) -> str | None:

        expression = expression.strip()

        if not expression:
            return None

        # literal: "/checkout/cart"
        if expression[0] in "\"'`":
            return AstReader.strip_quotes(expression)

        # member: checkoutRoutes.CART
        if "." in expression:

            holder, _, key = expression.rpartition(".")

            return self.table.get(holder, {}).get(key)

        # simple constant: CART_KEY, only when the name has a single value
        values = self.scalars.get(expression)

        if values and len(values) == 1:
            return next(iter(values))

        return None
