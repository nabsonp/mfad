"""
Self-contained, explorable HTML report.

A single file, with no CDN and no network. The SVG is generated here,
in Python: positions, curves and labels arrive ready, so the same
artifacts always produce the same drawing. The JavaScript only
transforms what is already on the page; without it the report still
shows the architecture and loses only the exploration.

The page is organized in four reading levels: numbers, map,
anti-patterns and inventory. The architecture comes first because
the anti-patterns are an annotation layer over it, not the other
way around.

Every text on the page comes from `i18n/texts.json`. The HTML is
emitted in English, with each text marked by its key; the language
button rebuilds the sentences in Portuguese from the same keys, without
going back to Python.
"""

from __future__ import annotations

import html
import json
from importlib import resources

from mfad.adapters.driven import i18n
from mfad.adapters.driven.i18n import mark, marker
from mfad.adapters.driven.visualization import payload, tables, views
from mfad.application.ports import Renderer
from mfad.domain import AntiPatternDetection, MicroFrontendArchitecture


def _asset(name: str) -> str:

    return (
        resources.files("mfad.adapters.driven.visualization.assets")
        .joinpath(name)
        .read_text(encoding="utf-8")
    )


def _json(value) -> str:
    """JSON inside `<script>`: `</` would close the tag too early."""

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
            # The architecture name is the same in both languages.
            title=html.escape(f"{project} - MFAD"),
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
            # The color of each anti-pattern, so the sidebar uses the same one.
            data=_json({**data, "colors": {item["anti_pattern"]: tables.color_of(item["anti_pattern"]) for item in data["detections"]}}),
            texts=_json(i18n.texts()),
        )

    @staticmethod
    def _language() -> str:
        """The language selector in the header."""

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
    # Level 1: numbers
    # ------------------------------------------------------------------

    #: The header numbers, in order.
    METRICS = (
        "microfrontends",
        "screens",
        "navigations",
        "compositions",
        "communications",
        "api_calls",
        "detections",
    )

    #: The tab each number opens. Fragments and compositions are the
    #: same table, so there is a single tab, the compositions one: two
    #: boxes for the same table would be selected together.
    OPENS = {"compositions": "fragments"}

    #: The pages besides the home one.
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
        The numbers, which are also the page's tabs.

        The first box leads to the map; each number leads to the table
        that adds it up.
        """

        counts = {
            "microfrontends": len(architecture.microfrontends),
            "screens": len(architecture.screens),
            "compositions": len(architecture.compositions),
            "navigations": len(architecture.navigations),
            "communications": sum(1 for item in architecture.communications if item.directed),
            # An endpoint is method and path: GET and POST on the same path
            # are two.
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
        """One page per header tab, besides the home one."""

        content = {
            "microfrontends": tables.microfrontends(data),
            "screens": tables.screens(architecture, data),
            "fragments": tables.fragments(architecture),
            "navigations": tables.navigations(architecture),
            "communications": tables.communications(architecture),
            # A single table: each call is in the endpoint's detail.
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
    # Level 2: map
    # ------------------------------------------------------------------

    @staticmethod
    def _controls() -> str:
        """
        Dashboard search and filters: they apply to all graphs at
        once. Zoom belongs to each graph and sits in its card.
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
        """The zoom buttons of a card; the last one enlarges the card."""

        def button(action: str, key: str, symbol: str | None = None) -> str:
            # With a symbol, the text goes in `title`; without one, the text is the label.
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
        One card per graph, one below the other and all in view: the
        dashboard answers the questions without tabs to switch. Only the
        graphs that have something to show go in; an empty card would
        look like a defect.
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
        The slice selector and the drawings of each slice.

        The slices go in `<template>`: the browser does not draw them
        until someone picks one, and a page with dozens of them opens
        as fast as one without.
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
    # Level 3: anti-patterns
    # ------------------------------------------------------------------

    def _detections(self, data: dict, architecture: MicroFrontendArchitecture) -> str:
        """
        One row per detection: the anti-pattern and who is involved.
        The detail brings the data the rule declared, each in its own
        field, the reason and the code, grouped by micro frontend and
        file.

        Route detections (`metadata.path`) of the same anti-pattern
        become a single row, with one block per route: there is one per
        shared route, and dozens of identical rows hid the others.
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

        # In the order of the first of each group; the others go into one row.
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
                    # Artifact from before the fields: the sentence, as it is.
                    else [(mark("detection.evidence"), self._text(item, "message", "span"))]
                )
                # The slices are the evidence of the global-state detection, and
                # more readable than the list of accesses: the code goes inside
                # each one.
                slices = [entry for entry in data["slices"] if entry["id"] in (metadata.get("slices") or {})]
                evidence = (
                    (mark("fact.slice_list"), tables.state_slices(slices, directories), True)
                    if slices
                    else None
                )

            # For routes, the callers are in each one; the list of all of them,
            # together, does not say who hammers which.
            if len(subjects) > 3 and not metadata.get("path"):
                fields.insert(0, (mark("detection.subjects"), tables.names(subjects), True))

            # The definition of the anti-pattern, for whoever evaluates it without knowing it.
            if item.get("reference"):
                fields.insert(0, (
                    mark("detection.catalog"),
                    f'<a href="{html.escape(item["reference"], quote=True)}" target="_blank" rel="noopener">'
                    + mark("detection.catalog_link")
                    + "</a>",
                ))

            if evidence:
                # The reason before the list: with dozens of routes or
                # slices, after it the reason ended up too far away.
                if item.get("explanation"):
                    fields.append((mark("detection.why"), self._text(item, "explanation", "span"), True))
                fields.append(evidence)

            rows.append(
                tables.Row(
                    [
                        tables.anti_pattern(item["anti_pattern"]),
                        tables.few(subjects),
                        None if evidence else (self._text(item, "explanation", "span") if item.get("explanation") else "—"),
                        # Without a location (nano, mega: the evidence is the
                        # size), the field does not appear empty.
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
                    # The indices of the row's detections: the sidebar
                    # leads to it through any of them.
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
        """The value of a field: translatable text, when it is a reference."""

        if isinstance(value, dict) and "key" in value:
            return mark(value)

        return html.escape(str(value))

    @staticmethod
    def _text(item: dict, field: str, tag: str, attrs: str = "") -> str:
        """
        A detection text: through the reference, when the rule left it
        in `metadata`, and translatable; otherwise, the stored sentence,
        as it is.
        """

        reference = ((item.get("metadata") or {}).get("text") or {}).get(field)

        if reference:
            return mark(reference, tag, attrs)

        return f"<{tag}{attrs}>{html.escape(item.get(field) or '')}</{tag}>"


TEMPLATE = """<!doctype html>
<html lang="en">
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

<!-- The details of what was clicked: closed until the first click. -->
<aside class="block side drawer" id="side" aria-hidden="true">
  <div class="drawer-bar">{back}{close}</div>
  <div id="side-body"></div>
</aside>

<div class="pages">{pages}</div>

<script type="application/json" id="mfad-data">{data}</script>
<script type="application/json" id="mfad-texts">{texts}</script>
<script>{js}</script>
</body>
</html>
"""
