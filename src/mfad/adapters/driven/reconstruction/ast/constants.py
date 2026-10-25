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
2. Só as formas `const X = {...}` e `const X = "literal"` são
   reconhecidas.
3. A resolução transitiva tem um teto de iterações.

A constante simples — `const CART_KEY = "cart"` — segue a mesma
indexação por nome, com uma proteção a mais: um nome declarado com
valores diferentes em lugares diferentes não resolve. É o que torna
seguro resolver também a constante importada de outro módulo sem
seguir o import: se o nome só tem um valor no repositório, é ele.
"""

from __future__ import annotations

from tree_sitter import Node

from mfad.adapters.driven.reconstruction.ast.reader import AstReader


class RouteConstantTable:
    """Tabela de constantes string do repositório."""

    MAX_PASSES = 10

    def __init__(self):
        self.table: dict[str, dict[str, str]] = {}

        # entradas cujo valor é outra referência, ex.:
        # routes.CART = checkoutRoutes.CART
        self.pending: dict[tuple[str, str], str] = {}

        #: `const X = "literal"` — nome → valores vistos
        self.scalars: dict[str, set[str]] = {}

    def index_file(self, root: Node, source: bytes) -> None:

        for node in AstReader.find_all(root, "variable_declarator"):

            name_node = node.child_by_field_name("name")
            value_node = node.child_by_field_name("value")

            if not name_node or not value_node:
                continue

            if name_node.type != "identifier":
                continue

            # `{ ... } as const` e `{ ... } satisfies T`: a anotação do
            # TypeScript embrulha o literal, que continua sendo o valor.
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
        """Só `const`: `let` e `var` podem ser reatribuídos."""

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

        # constante simples: CART_KEY, só quando o nome tem um valor só
        values = self.scalars.get(expression)

        if values and len(values) == 1:
            return next(iter(values))

        return None
