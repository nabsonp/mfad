"""
Propagação de constantes.

Reconhece objetos literais como:

    const checkoutRoutes = {
        CART: "/checkout/cart",
    };

para que `path={checkoutRoutes.CART}` possa ser resolvido.

Limitações conhecidas, relevantes para interpretar a cobertura
da ferramenta:

1. A tabela é indexada pelo nome do identificador, globalmente.
   Dois arquivos com uma `const routes` diferente colidem.
2. Só a forma `const X = {...}` é reconhecida.
3. A resolução transitiva tem um teto de iterações.
"""

from __future__ import annotations

from tree_sitter import Node

from damfe.adapters.driven.reconstruction.ast.reader import AstReader


class RouteConstantTable:
    """Tabela de constantes string do repositório."""

    MAX_PASSES = 10

    def __init__(self):
        self.table: dict[str, dict[str, str]] = {}

        # entradas cujo valor é outra referência, ex.:
        # routes.CART = checkoutRoutes.CART
        self.pending: dict[tuple[str, str], str] = {}

    def index_file(self, root: Node, source: bytes) -> None:

        for node in AstReader.find_all(root, "variable_declarator"):

            name_node = node.child_by_field_name("name")
            value_node = node.child_by_field_name("value")

            if not name_node or not value_node:
                continue

            if name_node.type != "identifier":
                continue

            if value_node.type != "object":
                continue

            holder = AstReader.text(name_node, source)

            self._index_object(holder, value_node, source)

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
        Resolve referências entre constantes, iterando até o
        ponto fixo. É o que faz `routes.CART = checkoutRoutes.CART`
        chegar em `/checkout/cart`.
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

        # membro: checkoutRoutes.CART
        if "." in expression:

            holder, _, key = expression.rpartition(".")

            return self.table.get(holder, {}).get(key)

        return None
