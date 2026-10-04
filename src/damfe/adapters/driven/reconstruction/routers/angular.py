"""
Rotas do Angular Router.

Escrito a partir da interface `Route` documentada em
https://angular.dev/api/router/Route — não de repositório algum.

Em Angular a rota é DADO, não marcação: um array de literais de
objeto. Isso a torna mais simples de ler que o `<Route>` do React,
e ao mesmo tempo traz duas coisas que o JSX não tem — o segmento é
relativo e precisa ser concatenado com o do pai, e o componente
pode chegar por `loadComponent`, que carrega o caminho do arquivo
dentro do próprio especificador.
"""

from __future__ import annotations

from pathlib import Path

from tree_sitter import Node

from damfe.adapters.driven.reconstruction.ast import (
    AstReader,
    ImportTable,
    ModuleResolver,
)
from damfe.domain import Screen


#: As chaves que fazem de um literal de objeto uma rota.
#:
#: `path` sozinho não basta: qualquer configuração tem um campo
#: chamado assim. O que caracteriza a rota é `path` junto de um
#: destino, e os destinos são exatamente estes na interface.
DESTINATIONS = (
    "component",
    "loadComponent",
    "children",
    "loadChildren",
    "redirectTo",
)


class AngularRouteReader:
    """As telas que um arquivo declara via Angular Router."""

    name = "angular-router"

    def __init__(self, context):
        self.context = context

    def screens_in(self, file_path: Path, owner: str) -> list[Screen]:

        try:
            root, source = self.context.reader.parse(file_path)
        except Exception:
            return []

        imports = ImportTable(root, source, file_path)

        found: list[Screen] = []

        for array in AstReader.find_all(root, "array"):

            # Um array aninhado é visitado de novo pela varredura, e
            # já foi percorrido como `children` do pai. Só os de
            # primeiro nível entram.
            if self._inside_route_array(array):
                continue

            if not self._is_route_array(array, source):
                continue

            found.extend(
                self._walk(array, source, imports, file_path, owner, "")
            )

        return found

    # ------------------------------------------------------------------

    def _walk(
        self,
        array: Node,
        source: bytes,
        imports: ImportTable,
        file_path: Path,
        owner: str,
        prefix: str,
    ) -> list[Screen]:

        found: list[Screen] = []

        for entry in array.named_children:

            if entry.type != "object":
                continue

            fields = self._fields(entry, source)

            segment = self._literal(fields.get("path"), source)

            route = self._join(prefix, segment)

            component, target = self._component(
                fields, source, imports, file_path
            )

            if component:
                found.append(
                    Screen(
                        component=component,
                        microfrontend=owner,
                        route=route,
                        route_expression=segment if segment is not None else "",
                        file=(
                            self.context.relative(target) if target else None
                        ),
                        line=entry.start_point.row + 1,
                    )
                )

            children = fields.get("children")

            if children is not None and children.type == "array":
                found.extend(
                    self._walk(
                        children, source, imports, file_path, owner, route
                    )
                )

        return found

    def _component(
        self,
        fields: dict[str, Node],
        source: bytes,
        imports: ImportTable,
        file_path: Path,
    ) -> tuple[str | None, Path | None]:
        """
        O componente da rota, pelas duas formas documentadas.

        `component: X` nomeia um símbolo, resolvido pelo import.
        `loadComponent: () => import('./x').then(m => m.X)` carrega
        o caminho do arquivo dentro do especificador, o que é mais
        direto: não depende da tabela de imports.
        """

        direct = fields.get("component")

        if direct is not None and direct.type == "identifier":

            name = AstReader.text(direct, source)

            return name, imports.file_for(name)

        lazy = fields.get("loadComponent")

        if lazy is not None:

            specifier = self._lazy_specifier(lazy, source)

            if specifier:

                return (
                    self._lazy_name(lazy, source)
                    or specifier.split("/")[-1],
                    ModuleResolver.resolve(specifier, file_path),
                )

        return None, None

    @staticmethod
    def _lazy_specifier(node: Node, source: bytes) -> str | None:
        """O módulo de `() => import('./x')`."""

        for call in AstReader.find_all(node, "call_expression"):

            function = call.child_by_field_name("function")

            if not function or AstReader.text(function, source) != "import":
                continue

            arguments = call.child_by_field_name("arguments")

            if not arguments:
                continue

            for child in arguments.named_children:

                if child.type == "string":
                    return AstReader.strip_quotes(
                        AstReader.text(child, source)
                    )

        return None

    @staticmethod
    def _lazy_name(node: Node, source: bytes) -> str | None:
        """O símbolo de `.then(m => m.MyComponent)`."""

        for member in AstReader.find_all(node, "member_expression"):

            prop = member.child_by_field_name("property")

            if prop is None:
                continue

            name = AstReader.text(prop, source)

            if name and name[0].isupper():
                return name

        return None

    # ------------------------------------------------------------------

    @classmethod
    def _is_route_array(cls, array: Node, source: bytes) -> bool:

        for entry in array.named_children:

            if entry.type != "object":
                continue

            fields = cls._fields(entry, source)

            if "path" in fields and any(
                key in fields for key in DESTINATIONS
            ):
                return True

        return False

    @classmethod
    def _inside_route_array(cls, array: Node) -> bool:

        current = array.parent

        while current is not None:

            if current.type == "array":
                return True

            current = current.parent

        return False

    @staticmethod
    def _fields(node: Node, source: bytes) -> dict[str, Node]:

        found = {}

        for pair in node.named_children:

            if pair.type != "pair":
                continue

            key = pair.child_by_field_name("key")
            value = pair.child_by_field_name("value")

            if key and value:
                found[
                    AstReader.strip_quotes(AstReader.text(key, source))
                ] = value

        return found

    @staticmethod
    def _literal(node: Node | None, source: bytes) -> str | None:

        if node is None or node.type != "string":
            return None

        return AstReader.strip_quotes(AstReader.text(node, source))

    @staticmethod
    def _join(prefix: str, segment: str | None) -> str | None:
        """
        Concatena o segmento ao do pai.

        Em Angular o `path` é RELATIVO — `path: 'info'` dentro de
        `path: 'product/:id'` responde por `/product/:id/info`. Ler
        o segmento isolado daria uma rota que não existe.
        """

        if segment is None:
            return prefix or None

        parts = [part for part in (prefix, segment) if part]

        joined = "/".join(parts).replace("//", "/")

        return "/" + joined.lstrip("/") if joined else "/"
