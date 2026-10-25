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

from mfad.adapters.driven.reconstruction.ast import (
    AstReader,
    ImportTable,
    ModuleResolver,
)
from mfad.domain import Screen


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

        # O arquivo que um `loadChildren` carrega responde abaixo da
        # rota que o carrega, não da raiz.
        prefixes = sorted(self._mounts().get(file_path.resolve(), {""}))

        for array in self._route_arrays(root, source):
            for prefix in prefixes:
                found.extend(
                    self._walk(array, source, imports, file_path, owner, prefix)
                )

        return found

    def _route_arrays(self, root: Node, source: bytes) -> list[Node]:

        # Um array aninhado é visitado de novo pela varredura, e
        # já foi percorrido como `children` do pai. Só os de
        # primeiro nível entram.
        return [
            array
            for array in AstReader.find_all(root, "array")
            if not self._inside_route_array(array) and self._is_route_array(array, source)
        ]

    # ------------------------------------------------------------------
    # loadChildren
    # ------------------------------------------------------------------

    def _mounts(self) -> dict[Path, set[str]]:
        """
        Arquivo → os caminhos em que um `loadChildren` o monta.

        `{ path: 'admin', loadChildren: () => import('./admin.routes') }`
        põe as rotas de `admin.routes` sob `/admin`
        (https://angular.dev/guide/ngmodules/lazy-loading). O carregado
        pode ser o arquivo das rotas ou o `NgModule` que as registra com
        `RouterModule.forChild`; neste caso, o prefixo passa aos arquivos
        de rotas que o módulo importa. Carregamentos encadeados somam os
        prefixos.
        """

        if self.context._angular_mounts is not None:
            return self.context._angular_mounts

        edges: list[tuple[Path, Path, str]] = []

        for file_path in self.context.tree.source_files():

            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            if "loadChildren" not in text:
                continue

            try:
                root, source = self.context.reader.parse(file_path)
            except Exception:
                continue

            for array in self._route_arrays(root, source):
                for target, route in self._lazy_children(array, source, file_path, ""):
                    edges.append((file_path.resolve(), target, route))

        # O `NgModule` carregado sem rotas próprias passa o prefixo a
        # quem ele importa e tem rotas.
        for _, target, _ in list(edges):

            try:
                root, source = self.context.reader.parse(target)
            except Exception:
                continue

            if self._route_arrays(root, source):
                continue

            imports = ImportTable(root, source, target)

            for local in imports.bindings:

                imported = imports.file_for(local)

                if imported is None:
                    continue

                try:
                    child_root, child_source = self.context.reader.parse(imported)
                except Exception:
                    continue

                if self._route_arrays(child_root, child_source):
                    edges.append((target, imported.resolve(), ""))

        mounts: dict[Path, set[str]] = {}

        for _ in range(10):

            changed = False

            for origin, target, route in edges:

                for base in mounts.get(origin, {""}):

                    joined = self._join(base, route) or ""

                    if joined not in mounts.setdefault(target, set()):
                        mounts[target].add(joined)
                        changed = True

            if not changed:
                break

        self.context._angular_mounts = mounts

        return mounts

    def _lazy_children(self, array: Node, source: bytes, file_path: Path, prefix: str) -> list[tuple[Path, str]]:
        """(arquivo carregado, rota) de cada `loadChildren` do array, com os `children` dentro."""

        found: list[tuple[Path, str]] = []

        for entry in array.named_children:

            if entry.type != "object":
                continue

            fields = self._fields(entry, source)

            route = self._join(prefix, self._literal(fields.get("path"), source)) or ""

            lazy = fields.get("loadChildren")

            if lazy is not None:

                # A forma antiga, em texto: `'./admin/admin.module#AdminModule'`.
                specifier = (
                    self._literal(lazy, source).split("#")[0]
                    if lazy.type == "string"
                    else self._lazy_specifier(lazy, source)
                )

                target = ModuleResolver.resolve(specifier, file_path) if specifier else None

                if target is not None:
                    found.append((target.resolve(), route))

            children = fields.get("children")

            if children is not None and children.type == "array":
                found.extend(self._lazy_children(children, source, file_path, route))

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
