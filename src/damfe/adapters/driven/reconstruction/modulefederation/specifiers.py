"""
Especificadores remotos: como um arquivo nomeia o módulo de outra unidade.

`hs-pharmacy/Pharmacy` quer dizer o módulo `./Pharmacy` publicado pela
unidade `hs-pharmacy`. O mesmo especificador aparece em import estático
e em `import()` dinâmico, e os dois precisam ser lidos — o dinâmico é
como um host carrega página remota.

Vive à parte porque duas etapas dependem dele: a extração de consumo de
fragmento e a atribuição de tela ao provedor.
"""

from __future__ import annotations

from tree_sitter import Node

from damfe.adapters.driven.reconstruction.ast import AstReader


def dynamic_imports(
    root: Node,
    source: bytes,
) -> list[tuple[str, str, int, str]]:
    """
    `const Pharmacy = lazy(() => import("hs-pharmacy/Pharmacy"))`.

    Devolve (módulo, nome local, linha, código). O nome local vem da
    declaração que envolve a chamada, que é por onde o componente é
    referenciado depois; sem declaração, cai no último segmento do
    especificador.
    """

    found = []

    for call in AstReader.find_all(root, "call_expression"):

        function = call.child_by_field_name("function")

        if not function or AstReader.text(function, source) != "import":
            continue

        arguments = call.child_by_field_name("arguments")

        if not arguments:
            continue

        literals = [
            child
            for child in arguments.named_children
            if child.type == "string"
        ]

        if not literals:
            continue

        module = AstReader.strip_quotes(
            AstReader.text(literals[0], source)
        )

        found.append(
            (
                module,
                binding(call, source) or module.split("/")[-1],
                call.start_point.row + 1,
                AstReader.text(call, source).strip(),
            )
        )

    return found


def binding(node: Node, source: bytes) -> str | None:
    """O nome declarado que envolve a chamada, se houver."""

    current = node.parent

    while current is not None:

        if current.type == "variable_declarator":

            name = current.child_by_field_name("name")

            return AstReader.text(name, source) if name else None

        if current.type in ("statement_block", "program"):
            return None

        current = current.parent

    return None


def split(module: str, catalog: dict[str, set[str]]) -> tuple[str | None, str]:
    """
    `app1/Botao` → (`app1`, `Botao`), quando as duas pontas batem.

    Casa o prefixo mais longo primeiro, porque o nome da unidade pode
    conter barra — `@org/app1/Botao` é a unidade `@org/app1` publicando
    `./Botao`.
    """

    parts = module.split("/")

    for cut in range(len(parts) - 1, 0, -1):

        candidate = "/".join(parts[:cut])
        rest = "/".join(parts[cut:])

        if rest in catalog.get(candidate, set()):
            return candidate, rest

    return None, ""
