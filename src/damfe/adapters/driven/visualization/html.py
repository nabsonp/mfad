"""
Relatório HTML autocontido e explorável.

Um arquivo só, sem CDN e sem rede. O SVG é gerado aqui, em
Python: posições, curvas e rótulos já chegam prontos, de modo que
os mesmos artefatos produzam sempre o mesmo desenho. O JavaScript
apenas transforma o que já está na página — sem ele o relatório
continua mostrando a arquitetura, perde só a exploração.

A página é organizada em quatro níveis de leitura: números,
mapa, anti-padrões e inventário. A arquitetura vem primeiro
porque os anti-padrões são uma camada de anotação sobre ela, e
não o contrário.
"""

from __future__ import annotations

import html
import json
from importlib import resources

from damfe.adapters.driven.visualization import layout, payload
from damfe.application.ports import Renderer
from damfe.domain import AntiPatternDetection, ArtifactSet


RELATION_LABELS = {
    "fragment_import": "composição",
    "navigation": "navegação",
    "communication": "comunicação",
}


def _asset(name: str) -> str:

    return (
        resources.files("damfe.adapters.driven.visualization.assets")
        .joinpath(name)
        .read_text(encoding="utf-8")
    )


class HtmlRenderer(Renderer):

    name = "html"

    extension = "html"

    def render(
        self,
        artifacts: ArtifactSet,
        detections: list[AntiPatternDetection] | None = None,
    ) -> str:

        detections = sorted(
            detections or [],
            key=lambda item: (item.rule, item.dimension, item.message),
        )

        data = payload.build(artifacts, detections)

        flagged = {
            subject
            for detection in detections
            for subject in detection.subjects
        }

        return TEMPLATE.format(
            css=_asset("report.css"),
            js=_asset("report.js"),
            project=html.escape(artifacts.project or "projeto"),
            metrics=self._metrics(artifacts, detections),
            tabs=self._tabs(data),
            svg=self._svg(artifacts, data, flagged),
            legend=self._legend(),
            endpoints=self._endpoints(data["endpoints"]),
            endpoints_count=len(data["endpoints"]),
            detections=self._detections(data["detections"]),
            detections_count=len(detections),
            inventory=self._inventory(data),
            microfrontends_count=len(artifacts.microfrontends),
            data=json.dumps(data, ensure_ascii=False),
        )

    # ------------------------------------------------------------------
    # Nível 1 — números
    # ------------------------------------------------------------------

    @staticmethod
    def _metrics(
        artifacts: ArtifactSet,
        detections: list[AntiPatternDetection],
    ) -> str:

        cards = [
            (len(artifacts.microfrontends), "micro frontends", False),
            (len(artifacts.screens), "telas", False),
            (len(artifacts.fragments), "fragmentos", False),
            (len(artifacts.fragment_imports), "composições", False),
            (len(artifacts.navigations), "navegações", False),
            (len(artifacts.communications), "comunicações", False),
            (len(artifacts.api_calls), "chamadas externas", False),
            (len(detections), "anti-padrões", bool(detections)),
        ]

        return "".join(
            f'<div class="metric{" alert" if alert else ""}">'
            f"<strong>{value}</strong><span>{label}</span></div>"
            for value, label, alert in cards
        )

    # ------------------------------------------------------------------
    # Nível 2 — mapa
    # ------------------------------------------------------------------

    @staticmethod
    def _tabs(data: dict) -> str:
        """
        Só as perspectivas que têm o que mostrar.

        Uma aba que abre num desenho vazio não informa que a
        relação não existe — parece defeito. A ausência da aba diz
        a mesma coisa sem ocupar espaço.
        """

        present = {edge["relation"] for edge in data["edges"]}

        tabs = [("all", "Todas")] + [
            (key, label)
            for key, label in payload.RELATIONS
            if key in present
        ]

        return "".join(
            f'<button class="tab" data-perspective="{key}" '
            f'aria-pressed="{"true" if key == "all" else "false"}">'
            f"{label}</button>"
            for key, label in tabs
        )

    def _svg(
        self,
        artifacts: ArtifactSet,
        data: dict,
        flagged: set[str],
    ) -> str:

        graph_nodes = [item["id"] for item in data["microfrontends"]]

        points = layout.positions_for(graph_nodes)

        if not points:
            return "<p class='empty body'>Nenhum micro frontend encontrado.</p>"

        parts = [
            f'<svg viewBox="0 0 {layout.WIDTH} {layout.HEIGHT}" '
            f'role="img" aria-label="Mapa da arquitetura">',
            self._markers(),
        ]

        parts.extend(self._edges(data, points))
        parts.extend(self._nodes(data, points, flagged))

        parts.append("</svg>")

        return "".join(parts)

    @staticmethod
    def _markers() -> str:

        colors = {
            "fragment_import": "#1d4ed8",
            "navigation": "#059669",
            "communication": "#be123c",
        }

        return "<defs>" + "".join(
            f'<marker id="arrow-{key}" viewBox="0 0 10 10" refX="9" '
            f'refY="5" markerWidth="7" markerHeight="7" '
            f'orient="auto-start-reverse">'
            f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{color}" /></marker>'
            for key, color in colors.items()
        ) + "</defs>"

    @staticmethod
    def _edges(data: dict, points: dict) -> list[str]:
        """
        Uma trilha por par de nós e relação.

        O traço fino recebe a cor; um traço transparente e largo
        por cima amplia a área de clique, que num arco de 2 px
        seria impossível de acertar.
        """

        grouped: dict[tuple[str, str, str], list[str]] = {}

        for edge in data["edges"]:

            key = (edge["source"], edge["target"], edge["relation"])

            grouped.setdefault(key, []).append(edge["label"] or "")

        bows = {
            "fragment_import": 0.16,
            "navigation": 0.26,
            "communication": 0.36,
            payload.DERIVED: 0.46,
        }

        parts = []

        for (source, target, relation), labels in sorted(grouped.items()):

            if source not in points or target not in points:
                continue

            path = layout.curve(
                points[source],
                points[target],
                bows.get(relation, 0.2),
            )

            edge_id = payload.edge_id(source, target, relation)

            title = html.escape(
                f"{payload.short(source)} → {payload.short(target)}: "
                + ", ".join(item for item in labels if item)
            )

            parts.append(
                f'<g class="edge-group" data-edge="{edge_id}" '
                f'data-relation="{relation}" '
                f'data-source="{html.escape(source)}" '
                f'data-target="{html.escape(target)}">'
                f'<path class="edge-hit" d="{path}" />'
                f'<path class="edge {relation}" d="{path}" '
                f'marker-end="url(#arrow-{relation})" />'
                f"<title>{title}</title>"
                f"</g>"
            )

        return parts

    @staticmethod
    def _nodes(data: dict, points: dict, flagged: set[str]) -> list[str]:

        parts = []

        for item in data["microfrontends"]:

            point = points.get(item["id"])

            if not point:
                continue

            classes = ["node"]

            if item["role"] == "shell":
                classes.append("shell")

            if item["id"] in flagged:
                classes.append("flagged")

            parts.append(
                f'<g class="{" ".join(classes)}" '
                f'data-id="{html.escape(item["id"])}" tabindex="0">'
                f'<circle cx="{point.x:.1f}" cy="{point.y:.1f}" '
                f'r="{layout.RADIUS}" />'
                f'<text x="{point.x:.1f}" y="{point.y - 5:.1f}">'
                f"{html.escape(item['short'])}</text>"
                f'<text class="meta" x="{point.x:.1f}" '
                f'y="{point.y + 11:.1f}">{len(item["screens"])} telas</text>'
                f'<text class="meta" x="{point.x:.1f}" '
                f'y="{point.y + 25:.1f}">'
                f'{len(item["fragments"])} frag.</text>'
                + (
                    f'<text class="role" x="{point.x:.1f}" '
                    f'y="{point.y - layout.RADIUS + 13:.1f}">'
                    f"orquestrador</text>"
                    if item["role"] == "shell"
                    else ""
                )
                + f"</g>"
            )

        return parts

    @staticmethod
    def _legend() -> str:

        keys = "".join(
            f'<span class="key">'
            f'<span class="swatch {key}" '
            f'style="border-bottom-color:{color}"></span>{label}</span>'
            for key, label, color in (
                ("mount", "montagem", "#6b7280"),
                ("fragment_import", "composição", "#1d4ed8"),
                ("navigation", "navegação", "#059669"),
                ("communication", "comunicação", "#be123c"),
                (payload.DERIVED, "backend compartilhado", "#b45309"),
            )
        )

        return (
            f'<div class="legend">{keys}'
            f'<span class="key" style="margin-left:auto">'
            f"contorno vermelho: aparece em alguma detecção · "
            f"roxo: orquestrador</span></div>"
        )

    # ------------------------------------------------------------------
    # Nível 3 — anti-padrões
    # ------------------------------------------------------------------

    def _detections(self, detections: list[dict]) -> str:

        if not detections:
            return (
                "<div class='body'><p class='empty'>"
                "Nenhum anti-padrão detectado.</p></div>"
            )

        return "<div class='body'>" + "".join(
            self._detection(item) for item in detections
        ) + "</div>"

    def _detection(self, item: dict) -> str:
        """
        A ordem das seções é fixa e deliberada:

            o que → onde → evidência → por quê → código

        Ela conduz da identificação do anti-padrão até o ponto no
        código-fonte, que é onde a rastreabilidade se fecha.
        """

        metadata = item.get("metadata") or {}

        chain = self._chain(metadata.get("chain") or [])

        return (
            f'<article class="detection">'
            # o que
            f"<header>"
            f"<h3>{html.escape(item['rule'])}</h3>"
            + (
                f'<span class="dimension">'
                f"{html.escape(item['dimension'])}</span>"
                if item.get("dimension")
                else ""
            )
            + f"</header>"
            # onde — a cadeia substitui a mensagem quando existe,
            # porque a mensagem a repetiria em prosa
            + (
                f'<p class="chain">{chain}</p>'
                if chain
                else f"<p>{html.escape(item['message'])}</p>"
            )
            # evidência
            + self._measures(item, metadata)
            # por quê
            + (
                f'<div class="why"><h4>Por que foi detectado</h4>'
                f"<p>{html.escape(item['explanation'])}</p></div>"
                if item.get("explanation")
                else ""
            )
            # código
            + self._locations(item)
            + f"<footer>"
            f'<button data-focus="{item["index"]}">Ver no grafo →</button>'
            f"</footer>"
            f"</article>"
        )

    @staticmethod
    def _chain(nodes: list) -> str:
        """Só as regras que declaram uma sequência ordenada."""

        return " → ".join(
            html.escape(payload.short(node)) for node in nodes
        )

    @staticmethod
    def _measures(item: dict, metadata: dict) -> str:
        """
        A evidência em números, numa linha só.

        O conteúdo vem do `metadata` que a regra declarou — por isso
        cada anti-padrão mostra o que lhe é próprio sem que a página
        conheça regra nenhuma.
        """

        measures = []

        subjects = item.get("subjects") or []

        if subjects:
            measures.append(f"{len(subjects)} micro frontends")

        if metadata.get("through"):
            # O que passa pela aresta muda com a relação: fragmento
            # na composição, rota na navegação, canal na comunicação.
            through = {
                "fragment_import": "fragmentos",
                "navigation": "rotas",
                "communication": "canais",
            }.get(metadata.get("relation"), "itens")

            measures.append(f"{len(metadata['through'])} {through}")

        if metadata.get("path"):
            measures.append(f"rota {metadata['path']}")

        if metadata.get("methods"):
            measures.append(", ".join(metadata["methods"]))

        if metadata.get("chain"):
            measures.append(f"{len(metadata['chain']) - 1} relações")

        if "coverage" in metadata:
            measures.append(
                f"centralidade {round(metadata['coverage'] * 100)}% "
                f"({metadata.get('neighbours')} de {metadata.get('others')})"
            )

        if metadata.get("providers"):
            measures.append(f"{len(metadata['providers'])} provedores")

        if metadata.get("screen"):
            measures.append(f"tela {metadata['screen']}")

        if not measures:
            return ""

        return (
            '<div class="measures"><h4>Evidência</h4><p>'
            + " · ".join(html.escape(item) for item in measures)
            + "</p></div>"
        )

    @staticmethod
    def _locations(item: dict) -> str:

        locations = item.get("locations") or []

        if not locations:
            return ""

        shown = locations[:6]

        rest = len(locations) - len(shown)

        return (
            '<div class="where"><h4>Código</h4><ul>'
            + "".join(
                f"<li><code>{html.escape(location['file'])}:"
                f"{location['line']}</code></li>"
                for location in shown
            )
            + (f"<li>e mais {rest}…</li>" if rest > 0 else "")
            + "</ul></div>"
        )

    @staticmethod
    def _endpoints(endpoints: list[dict]) -> str:
        """
        Endpoints ordenados por número de consumidores.

        Os compartilhados vêm primeiro: são o acoplamento por
        backend, que não aparece em nenhum dos outros grafos.
        """

        if not endpoints:
            return (
                "<div class='body'><p class='empty'>"
                "Nenhuma chamada externa encontrada.</p></div>"
            )

        rows = []

        for entry in endpoints:

            shared = len(entry["callers"]) > 1

            callers = ", ".join(
                payload.short(caller) for caller in entry["callers"]
            )

            rows.append(
                f"<tr>"
                f'<td class="mono">'
                f'{html.escape(", ".join(entry["methods"]))}</td>'
                f'<td class="name mono">{html.escape(entry["path"])}'
                + (
                    f'<span class="badge alert">compartilhado por '
                    f'{len(entry["callers"])}</span>'
                    if shared
                    else ""
                )
                + f"</td>"
                f"<td>{html.escape(callers)}</td>"
                f'<td class="num">{len(entry["callers"])}</td>'
                f"</tr>"
            )

        return (
            '<table class="inventory"><thead><tr>'
            "<th>método</th><th>endpoint</th><th>consumido por</th>"
            '<th class="num">consumidores</th>'
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
        )

    # ------------------------------------------------------------------
    # Nível 4 — inventário
    # ------------------------------------------------------------------

    @staticmethod
    def _inventory(data: dict) -> str:
        """
        Tabela, e não cartões: com dezenas de micro frontends,
        localizar um no grafo só visualmente deixa de funcionar.
        Entrada e saída aparecem aqui porque são a leitura que o
        desenho não dá de imediato.
        """

        rows = []

        for item in data["microfrontends"]:

            found = item["detections"]

            role = (
                '<span class="badge shell">shell</span>'
                if item["role"] == "shell"
                else ""
            )

            rows.append(
                f'<tr data-select="{html.escape(item["id"])}">'
                f'<td class="name">{html.escape(item["short"])}{role}</td>'
                f'<td>{len(item["screens"])}</td>'
                f'<td>{len(item["fragments"])}</td>'
                f'<td>{item["degree"]["in"]}</td>'
                f'<td>{item["degree"]["out"]}</td>'
                f'<td>{item["size"]["code_lines"]}</td>'
                f'<td class="flags">{found or "—"}</td>'
                f"</tr>"
            )

        return (
            '<table class="inventory"><thead><tr>'
            "<th>micro frontend</th>"
            '<th class="num">telas</th><th class="num">fragmentos</th>'
            '<th class="num">entradas</th><th class="num">saídas</th>'
            '<th class="num">linhas</th><th class="num">anti-padrões</th>' 
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
        )


TEMPLATE = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>damfe — arquitetura</title>
<style>{css}</style>
</head>
<body>

<header class="topbar">
  <div>
    <span class="eyebrow">Arquitetura</span>
    <h1>{project}</h1>
  </div>
  <span class="stamp">reconstruída por análise estática pelo damfe</span>
</header>

<div class="metrics">{metrics}</div>

<div class="layout">
  <div class="column">

    <section class="block">
      <header>
        <h2>Mapa arquitetural</h2>
        <div class="tabs">{tabs}</div>
      </header>
      <div class="controls">
        <input type="search" id="search" placeholder="buscar micro frontend">
        <label><input type="checkbox" id="only-flagged">
          só com anti-padrão</label>
        <span class="spacer"></span>
        <button class="ghost" id="reset-view">reposicionar</button>
      </div>
      <div class="stage" id="stage">
        <div class="focus-banner" id="focus-banner">
          <span id="focus-text"></span>
          <button id="clear-focus">sair do foco</button>
        </div>
        {svg}
      </div>
      {legend}
    </section>

    <section class="block">
      <header>
        <h2>Anti-padrões detectados</h2>
        <span class="count">{detections_count}</span>
      </header>
      {detections}
    </section>

    <section class="block">
      <header>
        <h2>Serviços externos</h2>
        <span class="count">{endpoints_count}</span>
      </header>
      {endpoints}
    </section>

    <section class="block">
      <header>
        <h2>Micro frontends</h2>
        <span class="count">{microfrontends_count}</span>
      </header>
      {inventory}
    </section>

  </div>

  <aside class="block side" id="side">
    <div class="body">
      <p class="placeholder">
        Clique num micro frontend ou numa relação do mapa para ver os
        detalhes. Use <strong>Ver no grafo</strong> numa detecção para
        isolar a evidência.
      </p>
    </div>
  </aside>
</div>

<script type="application/json" id="damfe-data">{data}</script>
<script>{js}</script>
</body>
</html>
"""
