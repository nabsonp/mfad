"""
Rotas do React Router e do @reach/router.

Escrito a partir da documentação das bibliotecas — não de repositório
algum:

- React Router v6/v7, rotas em JSX: https://reactrouter.com/6.30.0/components/route
- React Router v6.4+, rotas em objeto: https://reactrouter.com/6.30.0/route/route
  (`createBrowserRouter`, `useRoutes`, `RouteObject`)
- React Router v5: https://v5.reactrouter.com/web/api/Route
- @reach/router: https://reach.tech/router/api/Router

As quatro formas dizem a mesma coisa — este caminho mostra este
componente — de jeitos diferentes:

    <Route path="/a" element={<A />} />            v6, JSX
    { path: "/a", element: <A /> }                 v6.4+, objeto
    { path: "/a", Component: A }                   v6.4+, objeto
    { path: "/a", lazy: () => import("./a") }      v6.4+, carregada sob demanda
    <Route path="/a" component={A} />              v5
    <Route path="/a" render={() => <A />} />       v5
    <Route path="/a"><A /></Route>                 v5
    <Router><A path="/a" /></Router>               @reach/router

Ler só a primeira deixava sem tela todo projeto em v5, todo que usa
o roteador de dados e todo em @reach/router — e "sem tela" parece
resultado válido.

No v6 e no @reach/router a rota aninhada é RELATIVA à do pai; no v5,
cada `<Route>` traz o caminho inteiro. O caminho que começa com `/`
é absoluto nas três.
"""

from __future__ import annotations

from dataclasses import dataclass

from tree_sitter import Node

from damfe.adapters.driven.reconstruction.ast import AstReader, ImportTable
from damfe.adapters.driven.reconstruction.singlespa import jsx


#: Os atributos de `<Route>` que dizem o que ela mostra, por versão.
_ELEMENT = "element"  # v6: um elemento
_COMPONENT = ("component", "Component")  # v5 e v6.4: o componente
_RENDER = "render"  # v5: função que devolve o elemento

#: As chaves que fazem de um literal de objeto uma rota do React
#: Router. `component` sozinho também é a forma do Angular e do Vue,
#: que outro leitor cuida; aqui só o que é do React.
_OBJECT_TARGETS = ("element", "Component", "lazy")


#: Elementos que, renderizados por uma rota, mandam para outra: o
#: `<Redirect>` do v5 (https://v5.reactrouter.com/web/api/Redirect) e o
#: `<Navigate>` do v6 (https://reactrouter.com/6.30.0/components/navigate).
#: A rota que só redireciona não mostra tela nenhuma.
_REDIRECTS = frozenset({"Redirect", "Navigate"})


@dataclass
class RouteEntry:
    """Um par caminho → componente, ainda sem dono nem arquivo."""

    component: str
    expression: str
    route: str | None
    line: int

    #: `lazy: () => import("./x")` — o módulo, quando é por ele que
    #: a rota aponta para o componente.
    specifier: str | None = None


class ReactRouteReader:
    """As rotas que um arquivo declara via React Router ou @reach/router."""

    name = "react-router"

    def __init__(self, constants):
        self.constants = constants

    def routes_in(self, root: Node, source: bytes) -> list[RouteEntry]:

        found: list[RouteEntry] = []

        reach = self._reach_router_names(root, source)

        for element, opening in jsx.elements(root):

            tag = jsx.tag_name(opening, source)

            if tag == "Route":
                entry = self._jsx_route(element, opening, source)

            elif reach and self._inside_reach_router(element, source, reach):
                entry = self._reach_route(element, opening, source, reach)

            else:
                entry = None

            if entry:
                found.append(entry)

        for array in AstReader.find_all(root, "array"):

            if self._inside_array(array):
                continue

            found.extend(self._object_routes(array, source, ""))

        return found

    # ------------------------------------------------------------------
    # JSX
    # ------------------------------------------------------------------

    def _jsx_route(self, element: Node, opening: Node, source: bytes) -> RouteEntry | None:

        attributes = jsx.attributes(opening, source)

        component = (
            jsx.component_name(attributes.get(_ELEMENT, ""))
            or self._identifier(*(attributes.get(key, "") for key in _COMPONENT))
            or jsx.component_name(attributes.get(_RENDER, ""))
            or self._child_component(element, source)
        )

        if not component or component in _REDIRECTS:
            return None

        expression = attributes.get("path", "")

        # Sem `path` nem `index` a rota não tem caminho próprio: no v6
        # é rota de layout, no v5 é a que casa com tudo. Fica sem rota.
        if not expression and "index" not in attributes:
            route = None
        else:
            route = self._joined(element, source, expression or '""', "Route")

        return RouteEntry(
            component=component,
            expression=expression,
            route=route,
            line=element.start_point.row + 1,
        )

    def _child_component(self, element: Node, source: bytes) -> str | None:
        """v5: `<Route path="/a"><A /></Route>` — o filho é a tela."""

        if element.type != "jsx_element":
            return None

        for child in element.named_children:

            if child.type not in ("jsx_element", "jsx_self_closing_element"):
                continue

            opening = (
                child.child_by_field_name("open_tag")
                if child.type == "jsx_element"
                else child
            )

            name = jsx.tag_name(opening, source) if opening else None

            # Uma `<Route>` filha é aninhamento do v6, não tela.
            if name and name != "Route" and name[0].isupper() and name not in jsx.WRAPPERS:
                return name

        return None

    @staticmethod
    def _reach_router_names(root: Node, source: bytes) -> set[str]:
        """Os nomes locais de `Router` importados de @reach/router."""

        return {
            record.local_name
            for record in ImportTable.records(root, source)
            if record.module == "@reach/router" and record.imported_name == "Router"
        }

    def _inside_reach_router(self, element: Node, source: bytes, names: set[str]) -> bool:
        """No @reach/router a tela é filha DIRETA de `<Router>`, ou de outra tela."""

        parent = self._parent_element(element)

        while parent is not None:

            opening = (
                parent.child_by_field_name("open_tag")
                if parent.type == "jsx_element"
                else parent
            )

            name = jsx.tag_name(opening, source) if opening else None

            if name in names:
                return True

            # Aninhamento de rota: só continua subindo por outra tela
            # (elemento com `path`). Qualquer outra coisa no meio
            # significa que o elemento não é filho do roteador.
            if not opening or "path" not in jsx.attributes(opening, source):
                return False

            parent = self._parent_element(parent)

        return False

    def _reach_route(self, element: Node, opening: Node, source: bytes, names: set[str]) -> RouteEntry | None:

        attributes = jsx.attributes(opening, source)

        if "path" not in attributes and "default" not in attributes:
            return None

        component = jsx.tag_name(opening, source)

        if not component or not component[0].isupper():
            return None

        expression = attributes.get("path", "")

        return RouteEntry(
            component=component,
            expression=expression,
            route=(
                None
                if "default" in attributes
                else self._joined(element, source, expression, None)
            ),
            line=element.start_point.row + 1,
        )

    def _joined(self, element: Node, source: bytes, expression: str, tag: str | None) -> str | None:
        """
        O caminho inteiro, somando os pais quando o caminho é relativo.

        `tag` é a marca que identifica um pai que é rota: `Route` no
        React Router; no @reach/router, qualquer elemento com `path`.
        """

        own = self._resolve(expression)

        if own is None:
            return None

        parts = [own]

        current = self._parent_element(element)

        while current is not None and not parts[0].startswith("/"):

            opening = (
                current.child_by_field_name("open_tag")
                if current.type == "jsx_element"
                else current
            )

            if opening is not None and (tag is None or jsx.tag_name(opening, source) == tag):

                parent_expression = jsx.attributes(opening, source).get("path")

                if parent_expression is not None:

                    parent = self._resolve(parent_expression)

                    if parent is None:
                        return None

                    parts.insert(0, parent)

            current = self._parent_element(current)

        return _join(parts)

    @staticmethod
    def _parent_element(node: Node) -> Node | None:

        current = node.parent

        while current is not None and current.type != "jsx_element":
            current = current.parent

        return current

    # ------------------------------------------------------------------
    # Objetos
    # ------------------------------------------------------------------

    def _object_routes(self, array: Node, source: bytes, prefix: str) -> list[RouteEntry]:

        found: list[RouteEntry] = []

        for entry in array.named_children:

            if entry.type != "object":
                continue

            fields = _fields(entry, source)

            expression = (
                AstReader.text(fields["path"], source) if "path" in fields else ""
            )

            if not expression and "index" not in fields and "children" not in fields:
                continue

            segment = self._resolve(expression) if expression else ""

            route = None if segment is None else _join([prefix, segment] if not segment.startswith("/") else [segment])

            component, specifier = self._object_target(fields, source)

            if component and component not in _REDIRECTS and any(key in fields for key in _OBJECT_TARGETS):
                found.append(
                    RouteEntry(
                        component=component,
                        expression=expression,
                        route=route,
                        line=entry.start_point.row + 1,
                        specifier=specifier,
                    )
                )

            children = fields.get("children")

            if children is not None and children.type == "array" and route is not None:
                found.extend(self._object_routes(children, source, route))

        return found

    def _object_target(self, fields: dict[str, Node], source: bytes) -> tuple[str | None, str | None]:

        element = fields.get("element")

        if element is not None:
            return jsx.component_name(AstReader.text(element, source)), None

        component = fields.get("Component")

        if component is not None and component.type in ("identifier", "member_expression"):
            return AstReader.text(component, source), None

        lazy = fields.get("lazy")

        if lazy is not None:

            specifier = _imported_module(lazy, source)

            if specifier:
                return specifier.rstrip("/").split("/")[-1], specifier

        return None, None

    @staticmethod
    def _inside_array(array: Node) -> bool:
        """Array aninhado (`children`) é percorrido a partir do pai."""

        current = array.parent

        while current is not None:

            if current.type == "array":
                return True

            current = current.parent

        return False

    # ------------------------------------------------------------------

    def _resolve(self, expression: str) -> str | None:

        if not expression:
            return ""

        return self.constants.resolve(expression)

    @staticmethod
    def _identifier(*values: str) -> str | None:

        for value in values:

            value = value.strip()

            if value and (value[0].isupper() or "." in value) and value.replace(".", "").replace("_", "").isalnum():
                return value

        return None


def _fields(node: Node, source: bytes) -> dict[str, Node]:

    found: dict[str, Node] = {}

    for pair in node.named_children:

        if pair.type == "pair":

            key = pair.child_by_field_name("key")
            value = pair.child_by_field_name("value")

            if key and value:
                found[AstReader.strip_quotes(AstReader.text(key, source))] = value

        # `{ index: true }` e `{ path, element }` abreviados
        elif pair.type == "shorthand_property_identifier":
            found[AstReader.text(pair, source)] = pair

    return found


def _imported_module(node: Node, source: bytes) -> str | None:
    """O módulo de um `import("./x")` dentro da expressão."""

    for call in AstReader.find_all(node, "call_expression"):

        function = call.child_by_field_name("function")

        if not function or AstReader.text(function, source) != "import":
            continue

        arguments = call.child_by_field_name("arguments")

        for child in arguments.named_children if arguments else []:

            if child.type == "string":
                return AstReader.strip_quotes(AstReader.text(child, source))

    return None


def _join(parts: list[str]) -> str:

    segments = [part.strip("/") for part in parts if part and part.strip("/")]

    return "/" + "/".join(segments) if segments else "/"
