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

A forma JSON — `constructRoutes({ routes: [...] })` em JavaScript —
não é lida: ela é dado montado em tempo de execução, e resolvê-la
exigiria avaliar o módulo.
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
