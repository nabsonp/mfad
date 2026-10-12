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

Todo texto da página vem de `i18n/texts.json`. O HTML sai em
português, com cada texto marcado pela chave; o botão de idioma
refaz as frases em inglês a partir das mesmas chaves, sem voltar
ao Python.
"""

from __future__ import annotations

import html
import json
from importlib import resources

from damfe.adapters.driven import i18n
from damfe.adapters.driven.i18n import mark, marker
from damfe.adapters.driven.visualization import payload, tables, views
from damfe.application.ports import Renderer
from damfe.domain import AntiPatternDetection, MicroFrontendArchitecture


def _asset(name: str) -> str:

    return (
        resources.files("damfe.adapters.driven.visualization.assets")
        .joinpath(name)
        .read_text(encoding="utf-8")
    )


def _json(value) -> str:
    """JSON dentro de `<script>`: `</` fecharia a tag antes da hora."""

    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


class HtmlRenderer(Renderer):

    name = "html"

    extension = "html"

    def render(
        self,
        architecture: MicroFrontendArchitecture,
        detections: list[AntiPatternDetection] | None = None,
    ) -> str:

        detections = sorted(
            detections or [],
            key=lambda item: (item.anti_pattern, item.dimension, item.message),
        )

        data = payload.build(architecture, detections)

        flagged: dict[str, int] = {}

        for detection in detections:
            for subject in detection.subjects:
                flagged[subject] = flagged.get(subject, 0) + 1

        found = views.build(data, flagged)

        project = architecture.project or i18n.t("page.project")

        return TEMPLATE.format(
            css=_asset("report.css"),
            js=_asset("report.js"),
            # O nome da arquitetura é o mesmo nos dois idiomas.
            title=html.escape(f"{project} - DAMFE"),
            project=html.escape(project),
            language=self._language(),
            eyebrow=mark("page.eyebrow", "span", ' class="eyebrow"'),
            metrics=self._metrics(architecture, detections, data),
            controls=self._controls(),
            leave_focus=mark("map.leave_focus", "button", ' id="clear-focus"'),
            views=self._views(found),
            pages=self._pages(architecture, data, detections),
            hint=(
                f'<p class="hint"{marker("side.placeholder")} data-t-html="1">'
                f'{i18n.t("side.placeholder")}</p>'
            ),
            close=(
                f'<button class="drawer-close" id="side-close"{marker("side.close", "aria-label")} '
                f'aria-label="{html.escape(i18n.t("side.close"))}">×</button>'
            ),
            back=(
                f'<button class="drawer-back hidden" id="side-back"{marker("side.back", "aria-label")} '
                f'aria-label="{html.escape(i18n.t("side.back"))}">←</button>'
            ),
            # A cor de cada anti-padrão, para a barra lateral usar a mesma.
            data=_json({**data, "colors": {item["anti_pattern"]: tables.color_of(item["anti_pattern"]) for item in data["detections"]}}),
            texts=_json(i18n.texts()),
        )

    @staticmethod
    def _language() -> str:
        """O seletor de idioma do cabeçalho."""

        return (
            f'<div class="language" role="group"{marker("page.language", "aria-label")} '
            f'aria-label="{html.escape(i18n.t("page.language"))}">'
            + "".join(
                f'<button data-lang="{language}" '
                f'aria-pressed="{"true" if language == i18n.DEFAULT else "false"}">'
                f"{i18n.LABELS[language]}</button>"
                for language in i18n.LANGUAGES
            )
            + "</div>"
        )

    # ------------------------------------------------------------------
    # Nível 1 — números
    # ------------------------------------------------------------------

    #: Os números do cabeçalho, na ordem.
    METRICS = (
        "microfrontends",
        "screens",
        "navigations",
        "compositions",
        "communications",
        "api_calls",
        "detections",
    )

    #: A aba que cada número abre. Fragmentos e composições são a
    #: mesma tabela, então há uma aba só, a de composições: duas
    #: caixas para a mesma tabela ficavam selecionadas juntas.
    OPENS = {"compositions": "fragments"}

    #: As páginas além da inicial.
    PAGES = (
        "microfrontends",
        "screens",
        "navigations",
        "fragments",
        "communications",
        "api_calls",
        "detections",
    )

    @staticmethod
    def _metrics(
        architecture: MicroFrontendArchitecture,
        detections: list[AntiPatternDetection],
        data: dict,
    ) -> str:
        """
        Os números, que são também as abas da página.

        A primeira caixa leva ao mapa; cada número leva à tabela que
        o soma.
        """

        counts = {
            "microfrontends": len(architecture.microfrontends),
            "screens": len(architecture.screens),
            "compositions": len(architecture.compositions),
            "navigations": len(architecture.navigations),
            "communications": sum(1 for item in architecture.communications if item.directed),
            # Endpoint é método e caminho: GET e POST no mesmo caminho
            # são dois.
            "api_calls": len({(item.method, item.path) for item in architecture.api_calls}),
            "detections": len(detections),
        }

        home = (
            '<button class="metric home" role="tab" data-page="home" aria-selected="true">'
            '<strong><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">'
            '<path d="M3 11 12 3l9 8v10h-6v-6H9v6H3z" fill="currentColor"/></svg></strong>'
            + mark("page.home")
            + "</button>"
        )

        return home + "".join(
            f'<button class="metric{" alert" if metric == "detections" and counts[metric] else ""}" '
            f'role="tab" data-page="{HtmlRenderer.OPENS.get(metric, metric)}" aria-selected="false">'
            f"<strong>{counts[metric]}</strong>{mark(f'metric.{metric}')}</button>"
            for metric in HtmlRenderer.METRICS
        )

    def _pages(
        self,
        architecture: MicroFrontendArchitecture,
        data: dict,
        detections: list[AntiPatternDetection],
    ) -> str:
        """Uma página por aba do cabeçalho, além da inicial."""

        content = {
            "microfrontends": tables.microfrontends(data),
            "screens": tables.screens(architecture, data),
            "fragments": tables.fragments(architecture),
            "navigations": tables.navigations(architecture),
            "communications": tables.communications(architecture),
            # Uma tabela só: cada chamada está no detalhe do endpoint.
            "api_calls": tables.endpoints(data, architecture),
            "detections": self._detections(data, architecture),
        }

        titles = {page: f"page.title.{page}" for page in self.PAGES}
        titles["detections"] = "section.detections"

        return "".join(
            f'<div class="page hidden" data-page="{page}" role="tabpanel">'
            '<section class="block">'
            f"<header>{mark(titles[page], 'h2')}</header>"
            + mark(f"page.hint.{page}", "p", ' class="hint"')
            + content[page]
            + "</section></div>"
            for page in self.PAGES
        )

    # ------------------------------------------------------------------
    # Nível 2 — mapa
    # ------------------------------------------------------------------

    @staticmethod
    def _controls() -> str:
        """
        Busca e filtros do dashboard: valem para todos os grafos de uma
        vez. O zoom é de cada grafo e fica no card dele.
        """

        return (
            f'<input type="search" id="search"{marker("map.search", "placeholder")} '
            f'placeholder="{html.escape(i18n.t("map.search"))}">'
            f'<label><input type="checkbox" id="only-flagged"> {mark("map.only_flagged")}</label>'
            f'<label class="mount-toggle"><input type="checkbox" id="show-mount" checked> '
            f'{mark("map.mount")}</label>'
        )

    @staticmethod
    def _zoom() -> str:
        """Os botões de zoom de um card; o último amplia o card."""

        def button(action: str, key: str, symbol: str | None = None) -> str:
            # Com símbolo, o texto vai no `title`; sem, o texto é o rótulo.
            if symbol:
                return (
                    f'<button class="ghost" data-zoom="{action}"{marker(key, "title")} '
                    f'title="{html.escape(i18n.t(key))}">{symbol}</button>'
                )
            return mark(key, "button", f' class="ghost" data-zoom="{action}"')

        return (
            '<span class="zoom">'
            + button("out", "map.zoom_out", "−")
            + button("fit", "map.fit")
            + button("in", "map.zoom_in", "+")
            + button("expand", "map.expand")
            + "</span>"
        )

    @staticmethod
    def _views(found: list[views.View]) -> str:
        """
        Um card por grafo, um embaixo do outro e todos à vista: o
        dashboard responde às perguntas sem abas para alternar. Só os grafos que
        têm o que mostrar entram — um card vazio pareceria defeito.
        """

        if not found:
            return mark("map.empty", "p", ' class="empty body"')

        return "".join(
            f'<section class="block view" data-view="{view.id}">'
            f"<header>{mark(view.label, 'h2')}{HtmlRenderer._zoom()}</header>"
            + HtmlRenderer._variants(view)
            + f'<div class="viewport">{view.svg}</div>'
            + (mark(view.caption, "p", ' class="caption"') if view.caption else "")
            + view.legend
            + "</section>"
            for view in found
        )

    @staticmethod
    def _variants(view: views.View) -> str:
        """
        O seletor de recorte e os desenhos de cada recorte.

        Os recortes vão em `<template>`: o navegador não os desenha
        até alguém escolher um, e a página com dezenas deles abre tão
        rápido quanto sem.
        """

        if not view.variants:
            return ""

        options = "".join(
            f'<option value="{html.escape(key)}">{html.escape(payload.short(key))}</option>'
            for key in sorted(view.variants, key=payload.short)
        )

        templates = "".join(
            f'<template data-variant="{html.escape(key)}">{svg}</template>'
            for key, svg in sorted(view.variants.items())
        )

        everything = mark("variant.all", "option", ' value=""')

        return (
            f'<div class="variant-bar"><label>{mark("variant.label")} '
            f'<select class="variant">{everything}{options}</select>'
            f"</label>{mark('variant.hint')}</div>"
            + templates
        )

    # ------------------------------------------------------------------
    # Nível 3 — anti-padrões
    # ------------------------------------------------------------------

    def _detections(self, data: dict, architecture: MicroFrontendArchitecture) -> str:
        """
        Uma linha por detecção: o anti-padrão e quem está envolvido. O
        detalhe traz os dados que a regra declarou, cada um num campo,
        o porquê e o código, agrupado por micro frontend e arquivo.

        As detecções de rota (`metadata.path`) do mesmo anti-padrão
        viram uma linha só, com um bloco por rota: são uma por rota
        compartilhada, e dezenas de linhas iguais escondiam as outras.
        """

        detections = data["detections"]

        if not detections:
            return "<div class='body'>" + mark("empty.detections", "p", ' class="empty"') + "</div>"

        directories = {item["id"]: item["directory"] for item in data["microfrontends"]}

        columns = [
            tables.Column("detection.anti_pattern"),
            tables.Column("detection.subjects"),
            tables.Column("detection.why", summary=False, wide=True),
            tables.Column("detection.code", summary=False, wide=True),
        ]

        # Na ordem da primeira de cada grupo; as outras ficam numa só.
        groups: list[list[dict]] = []
        routes: dict[str, list[dict]] = {}

        for item in detections:

            if not (item.get("metadata") or {}).get("path"):
                groups.append([item])
            elif item["anti_pattern"] in routes:
                routes[item["anti_pattern"]].append(item)
            else:
                routes[item["anti_pattern"]] = [item]
                groups.append(routes[item["anti_pattern"]])

        rows = []

        for group in groups:

            item = group[0]

            metadata = item.get("metadata") or {}

            subjects = sorted({subject for entry in group for subject in entry.get("subjects") or []})

            if metadata.get("path"):
                paths = [entry["metadata"]["path"] for entry in group]
                fields = [(mark("fact.routes"), str(len(paths)))]
                evidence = (mark("fact.route_list"), tables.shared_endpoints(paths, data, architecture), True)
            else:
                facts = (metadata.get("text") or {}).get("facts")
                fields = (
                    [(mark(fact["label"]), self._value(fact["value"])) for fact in facts]
                    if facts
                    # Artefato de antes dos campos: a frase, como está.
                    else [(mark("detection.evidence"), self._text(item, "message", "span"))]
                )
                # As fatias são a evidência da detecção de estado global, e
                # mais legíveis que a lista de acessos: o código vai dentro
                # de cada uma.
                slices = [entry for entry in data["slices"] if entry["id"] in (metadata.get("slices") or {})]
                evidence = (
                    (mark("fact.slice_list"), tables.state_slices(slices, directories), True)
                    if slices
                    else None
                )

            # Nas rotas, quem chama está em cada uma; a lista de todos,
            # junta, não diz quem martela qual.
            if len(subjects) > 3 and not metadata.get("path"):
                fields.insert(0, (mark("detection.subjects"), tables.names(subjects), True))

            if evidence:
                # O porquê antes da lista: com dezenas de rotas ou de
                # fatias, depois dela ficava longe demais.
                if item.get("explanation"):
                    fields.append((mark("detection.why"), self._text(item, "explanation", "span"), True))
                fields.append(evidence)

            rows.append(
                tables.Row(
                    [
                        tables.anti_pattern(item["anti_pattern"]),
                        tables.few(subjects),
                        None if evidence else (self._text(item, "explanation", "span") if item.get("explanation") else "—"),
                        # Sem localização (nano, mega: a evidência é o
                        # tamanho), o campo não aparece vazio.
                        None
                        if evidence or not item.get("locations")
                        else tables.grouped(
                            [
                                (tables.owner_of(location["file"], directories), location["file"], location["line"], "")
                                for location in item.get("locations") or []
                            ],
                            directories,
                        ),
                    ],
                    fields=fields,
                    # Os índices das detecções da linha: a barra lateral
                    # leva a ela por qualquer um.
                    attrs={"data-key": " ".join([str(entry["index"]) for entry in group] + subjects)},
                    action=mark(
                        "detection.focus",
                        "button",
                        ' class="link-button go" data-focus="'
                        + ",".join(str(entry["index"]) for entry in group)
                        + '"',
                    ),
                )
            )

        return tables.table(columns, rows)

    @staticmethod
    def _value(value) -> str:
        """O valor de um campo: texto traduzível, quando é referência."""

        if isinstance(value, dict) and "key" in value:
            return mark(value)

        return html.escape(str(value))

    @staticmethod
    def _text(item: dict, field: str, tag: str, attrs: str = "") -> str:
        """
        Um texto da detecção: pela referência, quando a regra a deixou
        no `metadata`, e traduzível; senão, a frase gravada, como está.
        """

        reference = ((item.get("metadata") or {}).get("text") or {}).get(field)

        if reference:
            return mark(reference, tag, attrs)

        return f"<{tag}{attrs}>{html.escape(item.get(field) or '')}</{tag}>"


TEMPLATE = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{css}</style>
</head>
<body>

<header class="topbar">
  <div>
    {eyebrow}
    <h1>{project}</h1>
  </div>
  {language}
</header>

<nav class="metrics" role="tablist">{metrics}</nav>

<div class="page" data-page="home" role="tabpanel">
<div class="layout">
  <div class="column">

    <section class="block toolbar">
      <div class="controls">{controls}</div>
      {hint}
      <div class="focus-banner" id="focus-banner">
        <span id="focus-text"></span>
        {leave_focus}
      </div>
    </section>

    <div class="dashboard" id="stage">{views}</div>

  </div>
</div>
</div>

<!-- Os detalhes do que foi clicado: fechada até o primeiro clique. -->
<aside class="block side drawer" id="side" aria-hidden="true">
  <div class="drawer-bar">{back}{close}</div>
  <div id="side-body"></div>
</aside>

<div class="pages">{pages}</div>

<script type="application/json" id="damfe-data">{data}</script>
<script type="application/json" id="damfe-texts">{texts}</script>
<script>{js}</script>
</body>
</html>
"""
