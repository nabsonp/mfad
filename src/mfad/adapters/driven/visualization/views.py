"""
The map views, each one a ready SVG.

A single drawing, with all relations and all micro frontends, stops
being readable from about twenty units on: the edges cross in the
middle and the nodes overlap. Each question gets its own drawing,
with the arrangement that serves it:

- overview and one per pairwise relation (composition, navigation,
  communication), force-directed, only with those who take part;
- global state and backend, bipartite: what is shared becomes a
  node, and each participant links to it once;
- screens: where in the interface each relation happens.

The views are computed here, in Python, like the rest of the drawing;
the JavaScript only toggles which one is shown.
"""

from __future__ import annotations

import html
import math
from dataclasses import dataclass, field

from mfad.adapters.driven import i18n
from mfad.adapters.driven.i18n import mark
from mfad.adapters.driven.visualization import layout, payload
from mfad.adapters.driven.visualization.layout import Box


COLORS = {
    "mount": "#94a3b8",
    "composition": "#1d4ed8",
    "navigation": "#059669",
    "communication": "#be123c",
    "state": "#7c3aed",
    "backend": "#b45309",
}

#: Relations with a direction sentence between micro frontends. The direction
#: is that of the dependency: whoever depends points to whoever is used: the
#: fragment consumer to the provider, whoever navigates to the owner
#: of the route, whoever publishes to whoever subscribes. The sentences live in
#: `i18n/texts.json` (`direction.*` and `screen_direction.*`).
DIRECTED = ("mount", "composition", "navigation", "communication", "backend")

SCREEN_DIRECTED = ("composition", "navigation", "communication")


def meaning(relation: str, source: str, target: str, screens: bool = False) -> i18n.Ref:
    """The arrow sentence with the real names: `checkout displays a fragment of products`."""

    return i18n.ref(f"{'screen_direction' if screens else 'direction'}.{relation}", a=source, b=target)


def edge_title(relation: str, source: str, target: str, count: int, labels: str, screens: bool = False) -> str:
    """The `<title>` of an edge, translatable."""

    ref = i18n.ref(
        "edge.title",
        meaning=meaning(relation, source, target, screens),
        relation=i18n.ref(f"relation.{relation}"),
        n=count,
        labels=f": {labels[:300]}" if labels else "",
    )

    return mark(ref, "title")


#: How much each relation pulls the nodes in the arrangement. Mounting links the
#: orchestrator to everyone and, with the same weight as the others, would reduce
#: everything to a star.
WEIGHTS = {
    "mount": 0.35,
    "composition": 2.0,
    "navigation": 1.0,
    "communication": 1.5,
}


@dataclass
class View:
    """A view: the drawing, the legend and what it leaves out."""

    id: str

    #: key of the tab label
    label: str

    svg: str
    legend: str

    #: what the view leaves out, as a text reference
    caption: i18n.Ref | None = None

    #: Slices of the same view, one per micro frontend: the drawing only
    #: with it and with those related to it, arranged again.
    variants: dict[str, str] = field(default_factory=dict)


def escape(value) -> str:
    return html.escape(str(value), quote=True)


def markers(view: str) -> str:
    """
    Arrowheads, one per color, with an id specific to the view.

    With the same id in every view, `url(#arrow-…)` resolved to the
    marker of the first one, which is in a hidden tab, and a marker in
    a hidden element is not drawn: the other tabs ended up without
    arrows.
    """

    prefix = _marker_prefix(view)

    return "<defs>" + "".join(
        f'<marker id="{prefix}-{key}" viewBox="0 0 10 10" refX="9" refY="5" '
        f'markerUnits="userSpaceOnUse" markerWidth="13" markerHeight="13" '
        f'orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{color}" /></marker>'
        for key, color in COLORS.items()
    ) + "</defs>"


def _marker_prefix(view: str) -> str:
    return "arrow-" + "".join(character if character.isalnum() else "_" for character in view)


def legend(relations: list[str], extra: str = "", screens: bool = False) -> str:
    """
    Each relation with what its arrow means.

    The color tells the relation; without the sentence,
    `checkout → products` in composition does not say whether checkout
    shows products or the other way around.
    """

    directed = SCREEN_DIRECTED if screens else DIRECTED

    keys = "".join(
        f'<span class="key"><span class="swatch {key}"></span>'
        + mark(f"relation.{key}", "strong")
        + (
            '<span class="direction">A → B: '
            + mark(meaning(key, "A", "B", screens))
            + "</span>"
            if key in directed
            else ""
        )
        + "</span>"
        for key in relations
    )

    return f'<div class="legend">{keys}{extra}</div>'


def _svg(view: str, width: float, height: float, body: list[str], fit: str = "contain") -> str:
    """
    `fit` says how the drawing fits the window when opened: `contain`
    fully in view, for graphs; `width` only across the width, scrolling
    vertically, for long lists.
    """

    width = max(width, 320)
    height = max(height, 160)

    return (
        f'<svg class="graph" data-view="{view}" data-fit="{fit}" width="{width:.0f}" '
        f'height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'data-width="{width:.0f}" data-height="{height:.0f}" '
        f'role="img" aria-label="{escape(view)}">'
        + markers(view)
        + "".join(body).replace('url(#arrow-', f"url(#{_marker_prefix(view)}-")
        + "</svg>"
    )


# ----------------------------------------------------------------------
# Micro frontends as nodes
# ----------------------------------------------------------------------


def _mfe_size(item: dict) -> tuple[float, float]:

    meta = i18n.longest(_mfe_meta(item))

    return (
        max(layout.text_width(item["short"]) + 30, layout.text_width(meta, 10.5) + 30, 96),
        layout.NODE_HEIGHT,
    )


def _mfe_meta(item: dict) -> i18n.Ref:

    if item["role"] == "shell":
        return i18n.ref("node.shell")

    return i18n.ref("node.meta", screens=len(item["screens"]), fragments=len(item["fragments"]))


def _node_title(item: dict, count: int) -> str:

    if not count:
        return f"<title>{escape(item['id'])}</title>"

    return mark(i18n.ref("node.flagged", name=item["id"], n=count), "title")


def _mfe_node(item: dict, box: Box, flagged: dict[str, int]) -> str:

    classes = ["node"]

    if item["role"] == "shell":
        classes.append("shell")

    count = flagged.get(item["id"], 0)

    if count:
        classes.append("flagged")

    badge = (
        f'<g class="badge-count"><circle cx="{box.right - 2:.1f}" cy="{box.top + 2:.1f}" r="9" />'
        f'<text x="{box.right - 2:.1f}" y="{box.top + 5.5:.1f}">{count}</text></g>'
        if count
        else ""
    )

    return (
        f'<g class="{" ".join(classes)}" data-id="{escape(item["id"])}" tabindex="0">'
        f'<rect x="{box.left:.1f}" y="{box.top:.1f}" width="{box.w:.1f}" '
        f'height="{box.h:.1f}" rx="9" />'
        f'<text class="label" x="{box.x:.1f}" y="{box.y - 2:.1f}">{escape(item["short"])}</text>'
        + mark(_mfe_meta(item), "text", f' class="meta" x="{box.x:.1f}" y="{box.y + 12:.1f}"')
        + f"{badge}{_node_title(item, count)}</g>"
    )


# ----------------------------------------------------------------------
# Pairwise relations
# ----------------------------------------------------------------------


def pairs_view(
    view: str,
    label: str,
    data: dict,
    relations: list[str],
    flagged: dict[str, int],
    keep_isolated: bool,
) -> View | None:
    """
    Micro frontends linked by the chosen relations.

    One line per direction, pair and relation, with a single arrow.
    `A → B` and `B → A` are two arcs, one on each side of the straight
    line: a line with heads on both ends looked like a relation without
    direction, and composition, navigation and communication always
    have one. The thickness grows with the number of occurrences.
    """

    items = {item["id"]: item for item in data["microfrontends"]}

    grouped: dict[tuple[str, str, str], dict] = {}

    for edge in data["edges"]:

        if edge["relation"] not in relations:
            continue

        source, target = edge["source"], edge["target"]

        if source not in items or target not in items or source == target:
            continue

        entry = grouped.setdefault(
            (source, target, edge["relation"]),
            {"ids": set(), "labels": set(), "count": 0},
        )

        entry["ids"].add(edge["edge"])
        entry["count"] += 1

        if edge.get("label"):
            entry["labels"].add(edge["label"])

    if not grouped and not keep_isolated:
        return None

    involved = {a for a, _, _ in grouped} | {b for _, b, _ in grouped}

    nodes = sorted(items) if keep_isolated else sorted(involved)

    sizes = {node: _mfe_size(items[node]) for node in nodes}

    boxes, isolated, width, height = layout.force(
        sizes,
        [(a, b, WEIGHTS.get(relation, 1.0)) for a, b, relation in grouped],
    )

    body: list[str] = []

    if isolated:

        caption_y = height + (12 if boxes else layout.MARGIN)

        loose, loose_height = layout.grid(isolated, sizes, caption_y + 18, max(width, 900))

        boxes.update(loose)

        width = max(width, 900)

        body.append(
            mark(
                i18n.ref("svg.isolated", n=len(isolated)),
                "text",
                f' class="section" x="{layout.MARGIN}" y="{caption_y + 6:.1f}"',
            )
        )

        height = caption_y + 18 + loose_height + layout.MARGIN

    # Everything linking the same pair (different relations and both
    # directions) fans out, always measured in the orientation of the ordered
    # pair, so that no arc falls on top of another.
    fan: dict[tuple[str, str], list[tuple[str, str]]] = {}

    for source, target, relation in sorted(grouped):
        fan.setdefault(tuple(sorted((source, target))), []).append((relation, source))

    edges_svg = []

    for (source, target, relation), entry in sorted(grouped.items()):

        a, b = sorted((source, target))

        siblings = fan[(a, b)]

        index = siblings.index((relation, source))

        bow = 0.0 if len(siblings) == 1 else (index - (len(siblings) - 1) / 2) * 0.18

        # The arc is drawn from whoever acts to whoever receives; in the reverse
        # orientation, the same side of the line needs the curvature with the sign flipped.
        if source != a:
            bow = -bow

        path = layout.link(boxes[source], boxes[target], bow)

        width_px = 1.4 + min(3.0, math.log2(entry["count"] + 1) * 0.8)

        labels = ", ".join(sorted(entry["labels"]))

        edges_svg.append(
            f'<g class="edge-group" data-relation="{relation}" '
            f'data-edges="{escape(" ".join(sorted(entry["ids"])))}" '
            f'data-source="{escape(source)}" data-target="{escape(target)}">'
            f'<path class="edge-hit" d="{path}" />'
            f'<path class="edge {relation}" d="{path}" style="stroke-width:{width_px:.1f}px" '
            f'marker-end="url(#arrow-{relation})" />'
            + edge_title(relation, payload.short(source), payload.short(target), entry["count"], labels)
            + "</g>"
        )

    body = edges_svg + body + [
        _mfe_node(items[node], boxes[node], flagged) for node in nodes if node in boxes
    ]

    hidden = len(items) - len(nodes)

    return View(
        id=view,
        label=label,
        svg=_svg(view, width, height, body),
        legend=legend([relation for relation in relations if any(item[2] == relation for item in grouped)]),
        caption=i18n.ref("caption.hidden", n=hidden) if hidden and not keep_isolated else None,
    )


# ----------------------------------------------------------------------
# Bipartite: global state and backend
# ----------------------------------------------------------------------


def _slot_size(title: str, meta: str) -> tuple[float, float]:

    # Title in a mono font, slightly wider than the proportional one.
    return (
        max(len(title) * 7.4 + layout.text_width(meta, 10) + 34, 90),
        layout.ROW_HEIGHT - 6,
    )


def _slot(identifier: str, title: str, meta: str, box: Box, kind: str) -> str:

    return (
        f'<g class="slot {kind}" data-slot="{escape(identifier)}" tabindex="0">'
        f'<rect x="{box.left:.1f}" y="{box.top:.1f}" width="{box.w:.1f}" '
        f'height="{box.h:.1f}" rx="5" />'
        f'<text x="{box.left + 10:.1f}" y="{box.y + 4:.1f}">{escape(title)}'
        f'<tspan class="meta" dx="8">{escape(meta)}</tspan></text>'
        f"<title>{escape(title)} · {escape(meta)}</title></g>"
    )


def _row_node(item: dict, box: Box, flagged: dict[str, int]) -> str:
    """Micro frontend as a list row, for the column drawings."""

    count = flagged.get(item["id"], 0)

    classes = ["node", "row"] + (["shell"] if item["role"] == "shell" else []) + (
        ["flagged"] if count else []
    )

    return (
        f'<g class="{" ".join(classes)}" data-id="{escape(item["id"])}" tabindex="0">'
        f'<rect x="{box.left:.1f}" y="{box.top:.1f}" width="{box.w:.1f}" '
        f'height="{box.h:.1f}" rx="7" />'
        f'<text class="label" x="{box.x:.1f}" y="{box.y + 4:.1f}">{escape(item["short"])}</text>'
        + (
            f'<g class="badge-count"><circle cx="{box.right - 2:.1f}" cy="{box.top + 2:.1f}" r="8" />'
            f'<text x="{box.right - 2:.1f}" y="{box.top + 5.5:.1f}">{count}</text></g>'
            if count
            else ""
        )
        + f"<title>{escape(item['id'])}</title></g>"
    )


def _row_size(item: dict) -> tuple[float, float]:
    return (max(layout.text_width(item["short"]) + 28, 90), layout.ROW_HEIGHT - 6)


def state_view(data: dict, flagged: dict[str, int]) -> View | None:
    """
    Global-state slices and who touches them.

    An arrow to the slice is a write; an arrow to the micro frontend is
    a read. Two heads: reads and writes.
    """

    slices = data["slices"]

    if not slices:
        return None

    items = {item["id"]: item for item in data["microfrontends"]}

    left = {
        owner: _row_size(items[owner])
        for entry in slices
        for owner in entry["microfrontends"]
        if owner in items
    }

    right = {
        entry["id"]: _slot_size(entry["path"], entry["library"])
        for entry in slices
    }

    access: dict[tuple[str, str], set[str]] = {}

    for entry in slices:
        for item in entry["accesses"]:
            access.setdefault((item["microfrontend"], entry["id"]), set()).add(item["access"] or "read")

    boxes, width, height = layout.bipartite(left, right, sorted(access))

    body = []

    for (owner, slot), kinds in sorted(access.items()):

        if owner not in boxes or slot not in boxes:
            continue

        path = layout.sideways(boxes[owner], boxes[slot])

        ends = (
            (' marker-end="url(#arrow-state)"' if "write" in kinds else "")
            + (' marker-start="url(#arrow-state)"' if "read" in kinds else "")
        )

        verb = "state.both" if len(kinds) > 1 else f"state.{next(iter(kinds))}"

        body.append(
            f'<g class="edge-group" data-relation="state" data-slot="{escape(slot)}" '
            f'data-source="{escape(owner)}" data-target="{escape(slot)}">'
            f'<path class="edge-hit" d="{path}" />'
            f'<path class="edge state" d="{path}"{ends} />'
            + mark(i18n.ref(verb, a=payload.short(owner), b=slot), "title")
            + "</g>"
        )

    body += [_row_node(items[owner], boxes[owner], flagged) for owner in sorted(left)]

    body += [
        _slot(entry["id"], entry["path"], f'{entry["library"]} · {len(entry["microfrontends"])}', boxes[entry["id"]], "state")
        for entry in slices
    ]

    return View(
        id="state",
        label="tab.state",
        svg=_svg("state", width, height, body, "width"),
        legend=legend(
            ["state"],
            '<span class="key">' + mark("legend.state", "span", ' class="direction"') + "</span>",
        ),
        caption=i18n.ref("caption.state"),
    )


def backend_view(data: dict, flagged: dict[str, int]) -> View | None:
    """Endpoints consumed by more than one micro frontend, and who consumes them."""

    shared = [entry for entry in data["endpoints"] if len(entry["callers"]) > 1]

    if not shared:
        return None

    items = {item["id"]: item for item in data["microfrontends"]}

    left = {
        caller: _row_size(items[caller])
        for entry in shared
        for caller in entry["callers"]
        if caller in items
    }

    right = {
        entry["path"]: _slot_size(entry["path"], ", ".join(entry["methods"]))
        for entry in shared
    }

    links = sorted(
        (caller, entry["path"])
        for entry in shared
        for caller in entry["callers"]
        if caller in items
    )

    boxes, width, height = layout.bipartite(left, right, links)

    body = []

    for caller, path_id in links:

        path = layout.sideways(boxes[caller], boxes[path_id])

        body.append(
            f'<g class="edge-group" data-relation="backend" data-slot="{escape(path_id)}" '
            f'data-source="{escape(caller)}" data-target="{escape(path_id)}">'
            f'<path class="edge-hit" d="{path}" />'
            f'<path class="edge backend" d="{path}" marker-end="url(#arrow-backend)" />'
            + mark(meaning("backend", payload.short(caller), path_id), "title")
            + "</g>"
        )

    body += [_row_node(items[caller], boxes[caller], flagged) for caller in sorted(left)]

    body += [
        _slot(entry["path"], entry["path"], ", ".join(entry["methods"]), boxes[entry["path"]], "backend")
        for entry in shared
    ]

    alone = len(data["endpoints"]) - len(shared)

    return View(
        id="backend",
        label="tab.backend",
        svg=_svg("backend", width, height, body, "width"),
        legend=legend(["backend"]),
        caption=i18n.ref("caption.backend", n=alone) if alone else None,
    )


# ----------------------------------------------------------------------
# Screens
# ----------------------------------------------------------------------


def screens_view(data: dict, flagged: dict[str, int]) -> View | None:
    """The whole screens view, and one slice per micro frontend."""

    whole = _screens_svg(data, flagged, None)

    if whole is None:
        return None

    svg, present = whole

    screens = data["screens"]

    def owner(node: str) -> str:
        return screens[node]["microfrontend"] if node in screens else node

    involved = sorted(
        {owner(edge["source"]) for edge in data["screen_edges"]}
        | {owner(edge["target"]) for edge in data["screen_edges"]}
    )

    variants = {}

    for microfrontend in involved:
        found = _screens_svg(data, flagged, microfrontend)
        if found:
            variants[microfrontend] = found[0]

    return View(
        id="screens",
        label="tab.screens",
        svg=svg,
        legend=legend(present, mark("legend.screens", "span", ' class="key hint"'), screens=True),
        caption=i18n.ref("caption.screens"),
        variants=variants,
    )


def _screens_svg(data: dict, flagged: dict[str, int], focus: str | None) -> tuple[str, list[str]] | None:
    """
    Screens and fragments of each micro frontend, and the relations
    between them.

    Only those taking part in some relation between micro frontends go
    in: the screen that instantiates a fragment of another, the one
    that publishes or subscribes to a channel, the one navigated from
    and the one that receives. The rest of the screen inventory is in
    each micro frontend's panel.
    """

    screens = data["screens"]

    def owner_of(node: str) -> str:
        return screens[node]["microfrontend"] if node in screens else node

    edges = [
        edge
        for edge in data["screen_edges"]
        if focus is None or focus in (owner_of(edge["source"]), owner_of(edge["target"]))
    ]

    if not edges:
        return None

    items = {item["id"]: item for item in data["microfrontends"]}

    def owner(node: str) -> str:
        return screens[node]["microfrontend"] if node in screens else node

    involved = sorted({edge["source"] for edge in edges} | {edge["target"] for edge in edges})

    members: dict[str, list[str]] = {}

    for node in involved:
        members.setdefault(owner(node), []).append(node)

    def order(node: str) -> tuple:

        if node not in screens:
            return (2, "")

        item = screens[node]

        return (0 if item["kind"] == "screen" else 1, item["route"] or "~", item["name"])

    # Title and complement of each row: code text (name, route)
    # or a page text reference, which changes with the language.
    def text(node: str) -> tuple[str | i18n.Ref, str | i18n.Ref]:

        if node not in screens:
            return (i18n.ref("screen.outside"), "")

        item = screens[node]

        if item["kind"] == "fragment":
            return (item["name"], i18n.ref("screen.fragment"))

        return (item["name"], item["route"] or i18n.ref("screen.no_route"))

    def name(node: str) -> str | i18n.Ref:

        if node in screens:
            return screens[node]["name"]

        short = items[node]["short"] if node in items else payload.short(node)

        return i18n.ref("screen.outside_named", name=short)

    groups = []

    widths: dict[str, float] = {}

    for group_id in sorted(members):

        nodes = sorted(members[group_id], key=order)

        for node in nodes:
            title, meta = text(node)
            widths[node] = max(
                layout.text_width(_longest(title), 12.5) * 1.05
                + layout.text_width(_longest(meta), 10)
                + 36,
                120,
            )

        short = items[group_id]["short"] if group_id in items else payload.short(group_id)

        groups.append(
            layout.Group(
                id=group_id,
                title_width=layout.text_width(short, 13) + 40,
                members=[(node, widths[node]) for node in nodes],
            )
        )

    boxes, frames, width, height = layout.clusters(
        groups,
        [(edge["source"], edge["target"]) for edge in edges],
        {node: owner(node) for node in involved},
    )

    column = {node: frames[owner(node)].x for node in involved}

    # Frame below, edge on top: the arrowhead touches the
    # destination row, inside the frame, and underneath it the head vanished.
    body = []

    for group_id, frame in sorted(frames.items()):

        short = items[group_id]["short"] if group_id in items else payload.short(group_id)

        count = flagged.get(group_id, 0)

        body.append(
            f'<g class="cluster{" flagged" if count else ""}" data-id="{escape(group_id)}">'
            f'<rect x="{frame.x:.1f}" y="{frame.y:.1f}" width="{frame.w:.1f}" '
            f'height="{frame.h:.1f}" rx="10" />'
            f'<text class="title" x="{frame.x + 14:.1f}" y="{frame.y + 21:.1f}">{escape(short)}</text>'
            + (
                f'<g class="badge-count"><circle cx="{frame.x + frame.w - 14:.1f}" cy="{frame.y + 16:.1f}" r="8" />'
                f'<text x="{frame.x + frame.w - 14:.1f}" y="{frame.y + 19.5:.1f}">{count}</text></g>'
                if count
                else ""
            )
            + f"<title>{escape(group_id)}</title></g>"
        )

    for edge in edges:

        start, end = boxes[edge["source"]], boxes[edge["target"]]

        path = layout.sideways(start, end, column[edge["source"]] == column[edge["target"]])

        labels = ", ".join(edge["labels"])

        body.append(
            f'<g class="edge-group" data-relation="{edge["relation"]}" '
            f'data-screen-edge="{escape(edge["id"])}" '
            f'data-source="{escape(edge["source"])}" data-target="{escape(edge["target"])}" '
            f'data-mfes="{escape(owner(edge["source"]))} {escape(owner(edge["target"]))}">'
            f'<path class="edge-hit" d="{path}" />'
            f'<path class="edge {edge["relation"]}" d="{path}" marker-end="url(#arrow-{edge["relation"]})" />'
            + edge_title(
                edge["relation"],
                name(edge["source"]),
                name(edge["target"]),
                len(edge["items"]),
                labels,
                screens=True,
            )
            + "</g>"
        )

    for node in involved:

        box = boxes[node]

        title, meta = text(node)

        kind = screens[node]["kind"] if node in screens else "outside"

        body.append(
            f'<g class="screen-node {kind}" data-screen="{escape(node)}" '
            f'data-mfe="{escape(owner(node))}" tabindex="0">'
            f'<rect x="{box.left:.1f}" y="{box.top:.1f}" width="{box.w:.1f}" '
            f'height="{box.h:.1f}" rx="6" />'
            f'<text x="{box.left + 10:.1f}" y="{box.y + 4:.1f}">'
            + _piece(title, "tspan")
            + _piece(meta, "tspan", ' class="meta" dx="8"')
            + f"</text><title>{escape(node)}</title></g>"
        )

    present = sorted({edge["relation"] for edge in edges}, key=list(COLORS).index)

    view = "screens" if focus is None else f"screens:{focus}"

    return _svg(view, width, height, body, "width"), present


def _longest(value: str | i18n.Ref) -> str:
    return i18n.longest(value) if isinstance(value, dict) else value


def _piece(value: str | i18n.Ref, tag: str, attrs: str = "") -> str:
    """Code text, as it is, or page text, marked for translation."""

    if isinstance(value, dict):
        return mark(value, tag, attrs)

    return f"<{tag}{attrs}>{escape(value)}</{tag}>"


def build(data: dict, flagged: dict[str, int]) -> list[View]:
    """The views that have something to show, in tab order."""

    present = {edge["relation"] for edge in data["edges"]}

    views = [
        pairs_view(
            "overview",
            "tab.overview",
            data,
            ["mount", "composition", "navigation", "communication"],
            flagged,
            keep_isolated=True,
        )
    ]

    for relation, _ in payload.RELATIONS:

        if relation in present:
            views.append(
                pairs_view(relation, f"tab.{relation}", data, [relation], flagged, keep_isolated=False)
            )

    views.append(state_view(data, flagged))
    views.append(backend_view(data, flagged))
    views.append(screens_view(data, flagged))

    return [view for view in views if view is not None]
