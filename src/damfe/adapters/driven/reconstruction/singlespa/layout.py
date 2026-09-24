"""
Rotas declaradas por `single-spa-layout`.

Há duas maneiras de dizer qual aplicação responde por qual URL. A
usual é o `activeWhen` do `registerApplication`. A outra é o
single-spa-layout, que move essa decisão para um template:

    <template id="single-spa-layout">
      <single-spa-router>
        <route path="/produtos">
          <application name="@org/mfe-produtos"></application>
        </route>
      </single-spa-router>
    </template>

Sob um layout as aplicações NÃO precisam de `activeWhen` nenhum — o
motor de layout converte o `path` em função de atividade. Ler só o
registro, nesse caso, devolve o nome da aplicação e rota nenhuma, e o
resultado parece válido: um sistema inteiro sem donos de rota, sem
navegação e sem telas, sem nada indicando que faltou informação.

Aqui se lê o template e se recuperam os pares aplicação/rota. Rotas
aninhadas concatenam, como no single-spa-layout.

A forma JavaScript — `constructRoutes({ routes: [...] })` — é lida
quando o argumento é literal de objeto, que é como ela é escrita.
Argumento montado em variável ou vindo de outro módulo não é
resolvido: aí seria preciso avaliar o código.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path


class _LayoutReader(HTMLParser):
    """Percorre o template acumulando o caminho das rotas aninhadas."""

    def __init__(self):
        super().__init__(convert_charrefs=True)

        self.inside = False
        self.depth: list[str] = []
        self.found: dict[str, list[str]] = {}

    def handle_starttag(self, tag, attrs):

        values = dict(attrs)

        if tag == "template" and values.get("id") == "single-spa-layout":
            self.inside = True
            return

        if not self.inside:
            return

        if tag == "route":
            self.depth.append(values.get("path", "") or "")
            return

        if tag == "application":

            name = values.get("name")

            if name:
                self.found.setdefault(name, []).append(self._route())

    def handle_endtag(self, tag):

        if tag == "template":
            self.inside = False

        elif tag == "route" and self.depth:
            self.depth.pop()

    def _route(self) -> str:
        """Concatena os `path` das rotas que envolvem a aplicação."""

        parts = [part.strip("/") for part in self.depth if part.strip("/")]

        return "/" + "/".join(parts) if parts else "/"


def routes_by_application(repository: Path, tree) -> dict[str, list[str]]:
    """
    Aplicação → rotas, lidas dos templates de layout do repositório.

    Devolve vazio quando não há layout, que é o caso comum.
    """

    found: dict[str, list[str]] = {}

    for file_path in tree.markup_files():

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        if "single-spa-layout" not in content:
            continue

        reader = _LayoutReader()

        try:
            reader.feed(content)
        except Exception:
            continue

        for name, routes in reader.found.items():
            found.setdefault(name, []).extend(routes)

    return {name: sorted(set(routes)) for name, routes in found.items()}


def routes_from_construct(root, source, reader) -> dict[str, list[str]]:
    """
    Aplicação → rotas, lidas de `constructRoutes({ routes: [...] })`.

    A forma JavaScript do mesmo layout, equivalente ao template:

        constructRoutes({
          routes: [
            { type: "route", path: "/produtos", routes: [
              { type: "application", name: "@org/mfe-produtos" }
            ]}
          ]
        })

    Só literal de objeto é lido. `constructRoutes(minhaConfig)` fica
    de fora — resolver aquilo exigiria avaliar o módulo, e o que
    parece uma rota ali pode ser montado em tempo de execução.
    """

    found: dict[str, list[str]] = {}

    for call in reader.find_all(root, "call_expression"):

        function = call.child_by_field_name("function")
        arguments = call.child_by_field_name("arguments")

        if not function or not arguments:
            continue

        name = reader.text(function, source).split(".")[-1].strip()

        if name != "constructRoutes":
            continue

        for child in arguments.named_children:

            if child.type == "object":
                _walk_object(child, source, reader, [], found)

    return {name: sorted(set(routes)) for name, routes in found.items()}


def _walk_object(node, source, reader, depth, found) -> None:
    """Um nó da configuração: rota empilha caminho, aplicação registra."""

    fields = {}

    for pair in node.named_children:

        if pair.type != "pair":
            continue

        key_node = pair.child_by_field_name("key")
        value_node = pair.child_by_field_name("value")

        if key_node and value_node:
            fields[reader.strip_quotes(reader.text(key_node, source))] = (
                value_node
            )

    kind = (
        reader.strip_quotes(reader.text(fields["type"], source))
        if "type" in fields
        else ""
    )

    if kind == "application" or ("name" in fields and "path" not in fields):

        name = reader.strip_quotes(reader.text(fields["name"], source))

        if name:
            parts = [part.strip("/") for part in depth if part.strip("/")]

            found.setdefault(name, []).append(
                "/" + "/".join(parts) if parts else "/"
            )

        return

    nested = depth

    if "path" in fields:
        nested = depth + [
            reader.strip_quotes(reader.text(fields["path"], source))
        ]

    for key in ("routes", "children"):

        if key not in fields:
            continue

        for child in fields[key].named_children:

            if child.type == "object":
                _walk_object(child, source, reader, nested, found)
