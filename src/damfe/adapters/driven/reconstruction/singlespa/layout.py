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

O layout é lido nas duas formas que a documentação descreve: dentro de
`<template id="single-spa-layout">`, no HTML da página, e como arquivo
próprio cuja raiz é `<single-spa-router>` — o `microfrontend-layout.html`
que o `create-single-spa` gera e o código passa a
`constructRoutes(microfrontendLayout)`. Ler só a primeira deixava sem
rota todo sistema criado pelo gerador oficial.

`<route default>` responde quando nenhuma outra rota casa. Não é dono
de prefixo nenhum, então a aplicação entra no layout sem rota. O mesmo
vale para a aplicação fora de qualquer `<route>` — barra de navegação,
rodapé: fica sempre montada, e não é dona de URL nenhuma. Dar a ela a
rota `/` fazia todo `"/"` do código virar navegação para ela.

A forma JavaScript — `constructRoutes({ routes: [...] })` — é lida
quando o argumento é literal de objeto, que é como ela é escrita.
Argumento montado em variável ou vindo de outro módulo não é
resolvido: aí seria preciso avaliar o código.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path


class _LayoutReader(HTMLParser):
    """Percorre o layout acumulando o caminho das rotas aninhadas."""

    #: Os elementos que abrem um layout: o template na página, ou a
    #: raiz do arquivo de layout.
    ROOTS = ("template", "single-spa-router")

    def __init__(self):
        super().__init__(convert_charrefs=True)

        #: a tag que abriu o layout, enquanto dentro dele
        self.opened_by: str | None = None
        self.depth: list[str | None] = []
        self.found: dict[str, list[str]] = {}

    def handle_starttag(self, tag, attrs):

        values = dict(attrs)

        if self.opened_by is None:

            if tag == "template" and values.get("id") == "single-spa-layout":
                self.opened_by = tag

            elif tag == "single-spa-router":
                self.opened_by = tag

            return

        if tag == "route":
            # `None` marca a rota padrão: abaixo dela não há prefixo.
            self.depth.append(
                None if "default" in values else (values.get("path", "") or "")
            )
            return

        if tag == "application":

            name = values.get("name")

            if not name:
                return

            routes = self.found.setdefault(name, [])

            route = self._route()

            if route is not None:
                routes.append(route)

    def handle_endtag(self, tag):

        if tag == self.opened_by:
            self.opened_by = None

        elif tag == "route" and self.depth and self.opened_by:
            self.depth.pop()

    def _route(self) -> str | None:
        """Concatena os `path` das rotas que envolvem a aplicação."""

        if None in self.depth or not self.depth:
            return None

        parts = [part.strip("/") for part in self.depth if part.strip("/")]

        return "/" + "/".join(parts) if parts else "/"


def layouts(tree) -> dict[Path, dict[str, list[str]]]:
    """
    Arquivo → (aplicação → rotas), dos layouts do repositório.

    Por arquivo, e não somado, porque o layout também diz QUEM monta:
    o pacote que o contém é o orquestrador daquelas aplicações. Um
    repositório pode ter mais de um sistema, cada um com o seu.

    Devolve vazio quando não há layout, que é o caso comum.
    """

    found: dict[Path, dict[str, list[str]]] = {}

    for file_path in tree.markup_files():

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        if "single-spa-layout" not in content and "single-spa-router" not in content:
            continue

        reader = _LayoutReader()

        try:
            reader.feed(content)
        except Exception:
            continue

        if reader.found:
            found[file_path] = {
                name: sorted(set(routes)) for name, routes in reader.found.items()
            }

    return found


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
