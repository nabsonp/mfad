"""
The tables of each header tab: everything the numbers count.

The map answers who links to whom; the table answers how many, which
and where, row by row, with the file and line of each thing. Each
header number leads to the list that adds it up: a number that cannot
be opened asks for trust, one that can be opened can be checked.

The table shows few columns, the ones that identify the item; the rest
goes into a detail that the row opens when clicked. With all columns
side by side, the table did not fit on the screen and one had to
scroll sideways to read a single row. The detail also carries the
shortcut to the item on the map.

The tables come out of Python ready, like the rest of the page. The
script only filters, sorts and opens the rows that are already there.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field

from mfad.adapters.driven import i18n
from mfad.adapters.driven.i18n import mark, marker
from mfad.adapters.driven.visualization import payload
from mfad.domain import MicroFrontendArchitecture


@dataclass
class Column:

    #: header key in `texts.json`
    key: str

    numeric: bool = False

    #: in the row; the others go into the detail
    summary: bool = True

    #: in the detail, takes the full width: lists of paths do not fit
    #: in a grid column
    wide: bool = False


@dataclass
class Row:

    cells: list[str]

    #: the shortcut to the item on the map: (button text key, `data-go-*` attributes)
    go: tuple[str, dict[str, str]] | None = None

    #: `data-key` holds the row's keys, separated by spaces: the
    #: sidebar links find it through them
    attrs: dict[str, str] = field(default_factory=dict)

    #: fields of this row only, before the column ones: the label (already
    #: marked for translation), the value and, optionally, whether it takes
    #: the full width; for a table whose items do not all have the same
    #: fields, such as the detections
    fields: list[tuple] = field(default_factory=list)

    #: button in place of the `go` shortcut, for an action that is not going to a tab
    action: str = ""


def escape(value) -> str:
    return html.escape(str(value), quote=True)


def short(identifier: str) -> str:
    return escape(payload.short(identifier))


#: The color of each anti-pattern, fixed: the same name has the same color in
#: any system. The graph ones have the color of the relation that shows them
#: (global state violet, backend amber).
COLORS = {
    "cyclic-dependency": "red",
    "hub-like-dependency": "orange",
    "one-for-all": "pink",
    "hammering-apis": "amber",
    "global-state-communication": "violet",
    "mega-frontend": "blue",
    "nano-frontend": "cyan",
}

PALETTE = ("red", "orange", "pink", "amber", "violet", "blue", "cyan", "green", "slate")


def color_of(name: str) -> str:
    """The anti-pattern color; one not in the list gets one from its name."""

    return COLORS.get(name) or PALETTE[sum(map(ord, name)) % len(PALETTE)]


def anti_pattern(name: str) -> str:
    return f'<span class="ap-tag ap-{color_of(name)}">{escape(name)}</span>'


def names(identifiers) -> str:
    return ", ".join(short(item) for item in identifiers) or "—"


def few(identifiers, limit: int = 3) -> str:
    """
    The first names and how many are left, so the row fits on the
    screen; the full list goes into the detail.
    """

    identifiers = list(identifiers)

    if len(identifiers) <= limit:
        return names(identifiers)

    return names(identifiers[:limit]) + f' <span class="muted">+{len(identifiers) - limit}</span>'


def screen_names(identifiers) -> str:
    """`mfe#Tela` becomes `Tela`: the column already says which micro frontend it belongs to."""

    return ", ".join(escape(item.partition("#")[2] or item) for item in identifiers) or "—"


def where(file: str | None, line: int) -> str:

    if not file:
        return "—"

    return f"<code>{escape(file)}:{line}</code>" if line else f"<code>{escape(file)}</code>"


def place(screens: list[str], fragments: list[str]) -> str:
    """
    Where in the interface the code runs: the screens and fragments
    that reach it, or off-screen when none does.
    """

    parts = []

    if screens:
        parts.append(mark(i18n.ref("place.screens", names=", ".join(screens))))

    if fragments:
        parts.append(mark(i18n.ref("place.fragments", names=", ".join(fragments))))

    return " · ".join(parts) or mark("screen.outside", "span", ' class="muted"')


def grouped(entries: list[tuple[str, str | None, int, str]], roots: dict[str, str]) -> str:
    """
    Locations grouped by micro frontend and, within it, by file.

    Each entry is `(micro frontend, file, line, label)`; the label says
    what happens on that line (reads, imports, the method). The micro
    frontend appears once, as the group title, and its directory is
    stripped from the path. Each file appears once, with its lines next
    to it: the same file that imports and instantiates a fragment is a
    single row, not two separated by others. The full path goes in
    `title`.
    """

    if not entries:
        return "—"

    # Per file, the lines of each label together: three identical calls
    # in the same file are one label with three lines, not the
    # label repeated three times.
    groups: dict[str, dict[str | None, dict[str, list[int]]]] = {}

    for owner, file, line, label in entries:

        lines = groups.setdefault(owner, {}).setdefault(file, {}).setdefault(label, [])

        if line and line not in lines:
            lines.append(line)

    def hits(labels: dict[str, list[int]]) -> str:

        # The number right after the file, as `file:line`; what
        # happens there comes after.
        return '<span class="sep">·</span>'.join(
            '<span class="hit">'
            + (f'<span class="mono lines">{", ".join(f":{line}" for line in sorted(lines))}</span>' if lines else "")
            + (f" {label}" if label else "")
            + "</span>"
            for label, lines in labels.items()
        )

    def location(owner: str, file: str | None) -> str:

        if not file:
            return "—"

        root = (roots.get(owner) or "").rstrip("/")

        relative = file[len(root) + 1:] if root and file.startswith(root + "/") else file

        return f'<code title="{escape(file)}">{escape(relative)}</code>'

    return '<div class="locations">' + "".join(
        '<div class="location-group">'
        + (
            f'<div class="location-owner"><strong>{short(owner)}</strong>'
            + (
                f' <span class="muted mono">{escape(roots[owner].rstrip("/"))}/</span>'
                if roots.get(owner)
                else ""
            )
            + "</div>"
            if owner
            else ""
        )
        + "<ul>"
        + "".join(
            f'<li>{location(owner, file)}<span class="hits">{hits(labels)}</span></li>'
            for file, labels in files.items()
        )
        + "</ul></div>"
        for owner, files in groups.items()
    ) + "</div>"


def owner_of(file: str, directories: dict[str, str]) -> str:
    """The micro frontend of the file: the one with the longest directory that contains it."""

    candidates = [
        (len(directory), identifier)
        for identifier, directory in directories.items()
        if directory and (file == directory or file.startswith(directory.rstrip("/") + "/"))
    ]

    return max(candidates)[1] if candidates else ""


def roots(architecture: MicroFrontendArchitecture) -> dict[str, str]:
    return {item.id: item.directory for item in architecture.microfrontends}


def to_map(identifier: str) -> tuple[str, dict[str, str]]:
    return ("table.show_on_map", {"kind": "mfe", "target": identifier})


def table(columns: list[Column], rows: list[Row]) -> str:
    """
    The table with the filter and the count on top.

    Each item is two rows: the summary one, with the columns marked
    `summary`, and the detail one, hidden, with all columns and the
    shortcut to the map. A numeric column is sorted by number, not by
    text: "10" after "9".
    """

    if not rows:
        return mark("table.empty", "p", ' class="empty body"')

    summary = [index for index, column in enumerate(columns) if column.summary]
    detail = [index for index, column in enumerate(columns) if not column.summary]

    head = '<th class="chevron"></th>' + "".join(
        mark(
            columns[index].key,
            "th",
            ' class="num" data-sort="num"' if columns[index].numeric else ' data-sort="text"',
        )
        for index in summary
    )

    width = len(summary) + 1

    body = []

    for row in rows:

        attrs = "".join(f' {name}="{escape(value)}"' for name, value in row.attrs.items())

        body.append(
            f'<tr class="item"{attrs} tabindex="0"><td class="chevron"><span>›</span></td>'
            + "".join(
                f'<td class="num">{row.cells[index]}</td>' if columns[index].numeric else f"<td>{row.cells[index]}</td>"
                for index in summary
            )
            + "</tr>"
        )

        fields = "".join(
            ('<div class="wide">' if wide else "<div>") + f"<dt>{label}</dt><dd>{value}</dd></div>"
            for label, value, *rest in row.fields
            for wide in [bool(rest and rest[0])]
        ) + "".join(
            ("<div class=\"wide\">" if columns[index].wide else "<div>")
            + f"{mark(columns[index].key, 'dt')}<dd>{row.cells[index]}</dd></div>"
            for index in detail
            # `None` cell: the field does not apply to this row.
            if row.cells[index] is not None
        )

        go = row.action

        if row.go:

            key, data = row.go

            go = mark(
                key,
                "button",
                ' class="link-button go"'
                + "".join(f' data-go-{name}="{escape(value)}"' for name, value in data.items()),
            )

        body.append(
            f'<tr class="detail hidden"><td colspan="{width}">'
            f'<dl class="fields">{fields}</dl>{go}</td></tr>'
        )

    count = i18n.ref("table.count", n=len(rows), total=len(rows))

    return (
        '<div class="table-tools">'
        f'<input type="search" class="table-filter"{marker("table.filter", "placeholder")} '
        f'placeholder="{escape(i18n.t("table.filter"))}">'
        + mark(count, "span", ' class="table-count"')
        + mark("table.toggle", "span", ' class="table-hint"')
        + "</div>"
        f'<div class="table-scroll"><table class="inventory data"><thead><tr>{head}</tr></thead>'
        f"<tbody>{''.join(body)}</tbody></table></div>"
    )


# ----------------------------------------------------------------------
# One table per tab
# ----------------------------------------------------------------------


def _listing(entries) -> str:

    entries = list(entries)

    if not entries:
        return "—"

    return '<ul class="listing">' + "".join(f"<li>{entry}</li>" for entry in entries) + "</ul>"


def microfrontends(data: dict) -> str:

    columns = [
        Column("col.microfrontend"),
        Column("col.role"),
        Column("col.screens", True),
        Column("col.fragments", True),
        Column("col.detections", True),
        Column("col.routes", summary=False),
        Column("col.incoming", True, summary=False),
        Column("col.outgoing", True, summary=False),
        Column("col.lines", True, summary=False),
        Column("col.files", True, summary=False),
        Column("col.origin", summary=False),
    ]

    rows = [
        Row(
            [
                f'<strong>{short(item["id"])}</strong>',
                mark("value.shell" if item["role"] == "shell" else "value.microfrontend"),
                str(len(item["screens"])),
                str(len(item["fragments"])),
                str(item["detections"]),
                ", ".join(f"<code>{escape(route)}</code>" for route in item["routes"]) or "—",
                str(item["degree"]["in"]),
                str(item["degree"]["out"]),
                str(item["size"]["code_lines"]),
                str(item["size"]["files"]),
                where(item["entrypoint"] or item["directory"], 0),
            ],
            to_map(item["id"]),
            attrs={"data-key": item["id"]},
            # What the micro frontend defines, with the count in the label.
            fields=[
                (
                    mark(i18n.ref("list.screens", n=len(item["screens"]))),
                    _listing(
                        escape(screen["component"])
                        + (f' <code>{escape(screen["route"])}</code>' if screen["route"] else "")
                        for screen in item["screens"]
                    ),
                    True,
                ),
                (
                    mark(i18n.ref("list.fragments", n=len(item["fragments"]))),
                    _listing(escape(fragment["name"]) for fragment in item["fragments"]),
                    True,
                ),
            ],
        )
        for item in data["microfrontends"]
    ]

    return table(columns, rows)


def screens(architecture: MicroFrontendArchitecture, data: dict) -> str:

    # Only a screen that takes part in some relation is in the Screens tab; the
    # others lead to the micro frontend.
    related = {edge["source"] for edge in data["screen_edges"]} | {
        edge["target"] for edge in data["screen_edges"]
    }

    # The fragments of other micro frontends that each screen instantiates:
    # what the screen shows that is not its own.
    mounted: dict[str, list[str]] = {}

    for item in architecture.compositions:
        for render in item.renders:
            for screen in render.screens:
                entry = f"<strong>{escape(item.fragment)}</strong> <span class=\"muted\">({short(item.provider)})</span>"
                if entry not in mounted.setdefault(screen, []):
                    mounted[screen].append(entry)

    columns = [
        Column("col.microfrontend"),
        Column("col.screen"),
        Column("col.route"),
        Column("col.mounted_here"),
        Column("col.in_use", summary=False),
        Column("col.file", summary=False, wide=True),
    ]

    rows = [
        Row(
            [
                short(microfrontend.id),
                f"<strong>{escape(screen.component)}</strong>",
                f"<code>{escape(screen.route)}</code>" if screen.route else "—",
                "<br>".join(mounted.get(screen.id, [])) or "—",
                mark("value.yes" if screen.reachable else "value.no"),
                where(screen.file, screen.line),
            ],
            ("table.show_screen", {"kind": "screen", "target": screen.id})
            if screen.id in related
            else to_map(microfrontend.id),
            attrs={"data-key": f"{screen.id} {microfrontend.id}"},
        )
        for microfrontend in architecture.microfrontends
        for screen in microfrontend.screens
    ]

    return table(columns, rows)


def fragments(architecture: MicroFrontendArchitecture) -> str:
    """
    Fragments and compositions in a single table: one row per fragment.

    A composition is the fragment seen from whoever mounts it. In
    separate tables, knowing which screens a fragment appears on
    required crossing the two; here the row already says it, and the
    detail brings each composition: the consumer, where it imports and
    where it instantiates.
    """

    by_fragment: dict[tuple[str, str], list] = {}

    for item in architecture.compositions:
        by_fragment.setdefault((item.provider, item.fragment), []).append(item)

    exposed = [
        (microfrontend.id, fragment.name, fragment.file, fragment.line)
        for microfrontend in architecture.microfrontends
        for fragment in microfrontend.fragments
    ]

    # A composed fragment that extraction did not list as exposed also
    # goes in: no composition may disappear from the table.
    known = {(provider, name) for provider, name, _, _ in exposed}

    exposed += [
        (provider, name, None, 0)
        for provider, name in sorted(by_fragment)
        if (provider, name) not in known
    ]

    columns = [
        Column("col.fragment"),
        Column("col.provider"),
        # Who mounts it is a list that grows with reuse: the row keeps the
        # count, which sorts; the names go into the detail.
        Column("col.compositions", True),
        Column("col.mounted_on"),
        # Who mounts it is already the title of each group in "composed in".
        Column("col.defined_at", summary=False, wide=True),
        Column("col.composed_at", summary=False, wide=True),
    ]

    directories = roots(architecture)

    rows = []

    for provider, name, file, line in exposed:

        uses = by_fragment.get((provider, name), [])

        consumers = sorted({item.consumer for item in uses})

        screens = []

        for item in uses:
            for render in item.renders:
                for screen in render.screens:
                    label = (
                        f"{escape(screen.partition('#')[2] or screen)} "
                        f'<span class="muted">({short(item.consumer)})</span>'
                    )
                    if label not in screens:
                        screens.append(label)

        detail = grouped(
            [
                (item.consumer, item.imported_at.file, item.imported_at.line, mark("col.imported_at", "span", ' class="tag"'))
                for item in uses
            ]
            + [
                (item.consumer, render.file, render.line, mark("col.rendered_at", "span", ' class="tag"'))
                for item in uses
                for render in item.renders
            ],
            directories,
        )

        rows.append(
            Row(
                [
                    f"<strong>{escape(name)}</strong>",
                    short(provider),
                    str(len(uses)),
                    "<br>".join(screens) or "—",
                    where(file, line),
                    detail,
                ],
                _relation(uses[0].consumer, provider, "composition")
                if len(consumers) == 1
                else to_map(provider),
                attrs={
                    "data-key": " ".join(
                        [f"{provider}#{name}", provider] + [f"{consumer}>{provider}" for consumer in consumers]
                    )
                },
            )
        )

    return table(columns, rows)


def _relation(source: str, target: str, relation: str) -> tuple[str, dict[str, str]]:
    """The shortcut to the edge: the relation's tab, with its panel open."""

    return (
        "table.show_relation",
        {"kind": "edge", "target": payload.edge_id(source, target, relation), "view": relation, "source": source},
    )


def navigations(architecture: MicroFrontendArchitecture) -> str:

    columns = [
        Column("col.source"),
        Column("col.target"),
        Column("col.url"),
        Column("col.match", summary=False),
        Column("col.from_screens", summary=False),
        Column("col.at", summary=False),
    ]

    rows = [
        Row(
            [
                short(item.source),
                short(item.target),
                f"<code>{escape(item.resolved_url or item.expression)}</code>",
                _match(item.match),
                screen_names(item.on.screens + item.on.fragments),
                where(item.at.file, item.at.line)
                + (f'<br><code class="muted">{escape(item.at.code)}</code>' if item.at.code else ""),
            ],
            _relation(item.source, item.target, "navigation"),
            attrs={"data-key": f"{item.source}>{item.target}"},
        )
        for item in architecture.navigations
    ]

    return table(columns, rows)


def communications(architecture: MicroFrontendArchitecture) -> str:
    """Only the meaningful ones: global state is in the slices tab."""

    columns = [
        Column("col.source"),
        Column("col.target"),
        Column("col.channel"),
        Column("col.mechanism", summary=False),
        Column("col.produced_at", summary=False, wide=True),
        Column("col.consumed_at", summary=False, wide=True),
        Column("col.source_screens", summary=False),
        Column("col.target_screens", summary=False),
    ]

    directories = roots(architecture)

    rows = [
        Row(
            [
                short(item.source),
                short(item.target),
                f"<code>{escape(item.channel)}</code>",
                escape(item.mechanism),
                grouped([(item.source, at.file, at.line, "") for at in item.produced_at], directories),
                grouped([(item.target, at.file, at.line, "") for at in item.consumed_at], directories),
                screen_names(item.produced_on.screens + item.produced_on.fragments),
                screen_names(item.consumed_on.screens + item.consumed_on.fragments),
            ],
            _relation(item.source, item.target, "communication"),
            attrs={"data-key": f"{item.source}>{item.target}"},
        )
        for item in architecture.communications
        if item.directed
    ]

    return table(columns, rows)


def state_slices(entries: list[dict], directories: dict[str, str]) -> str:
    """
    The global-state slices, each with who reads, who writes and
    where, grouped by micro frontend and file.

    It lives in the detail of the global-state detection: it is its
    evidence, and a separate tab repeated what the detection already
    says.
    """

    if not entries:
        return "—"

    blocks = []

    for entry in entries:

        readers = sorted({item["microfrontend"] for item in entry["accesses"] if item["access"] != "write"})
        writers = sorted({item["microfrontend"] for item in entry["accesses"] if item["access"] == "write"})

        # Each slice is closed: with dozens of accesses, all open pushed
        # the detection's reason far away. The closed row
        # already says how many micro frontends and how many accesses it has.
        blocks.append(
            '<details class="slice">'
            '<summary class="slice-head"><span class="caret">›</span>'
            f'<code><strong>{escape(entry["path"])}</strong></code>'
            f' <span class="muted">{escape(entry["library"])}</span>'
            + mark(
                i18n.ref(
                    "slice.summary",
                    mfes=len(entry["microfrontends"]),
                    n=len(entry["accesses"]),
                ),
                "span",
                ' class="muted slice-count"',
            )
            + "</summary>"
            '<dl class="slice-roles">'
            f"<div><dt>{mark('col.readers')}</dt><dd>{names(readers)}</dd></div>"
            f"<div><dt>{mark('col.writers')}</dt><dd>{names(writers)}</dd></div>"
            "</dl>"
            + grouped(
                [
                    (item["microfrontend"], item["file"], item["line"], _access(item["access"]))
                    for item in entry["accesses"]
                ],
                directories,
            )
            + "</details>"
        )

    return '<div class="slices">' + "".join(blocks) + "</div>"


def endpoints(data: dict, architecture: MicroFrontendArchitecture) -> str:
    """The endpoints, shared ones first: they are the backend coupling."""

    columns = [
        Column("col.method"),
        Column("col.path"),
        Column("col.callers", True),
        Column("table.consumed_by", summary=False),
        Column("col.called_from", summary=False, wide=True),
    ]

    directories = roots(architecture)

    calls: dict[str, list] = {}

    for item in architecture.api_calls:
        calls.setdefault(item.path, []).append(item)

    rows = []

    for entry in data["endpoints"]:

        shared = len(entry["callers"]) > 1

        rows.append(
            Row(
                [
                    f'<span class="mono">{escape(", ".join(entry["methods"]))}</span>',
                    f"<code>{escape(entry['path'])}</code>"
                    + (
                        mark(i18n.ref("table.shared_by", n=len(entry["callers"])), "span", ' class="badge alert"')
                        if shared
                        else ""
                    ),
                    str(len(entry["callers"])),
                    names(entry["callers"]),
                    _calls(calls.get(entry["path"], []), directories),
                ],
                # Only the shared one is in the Backend tab.
                ("table.show_endpoint", {"kind": "slot", "target": entry["path"], "view": "backend"})
                if shared
                else to_map(entry["callers"][0]),
                attrs={"data-key": entry["path"]},
            )
        )

    return table(columns, rows)


def _calls(calls: list, directories: dict[str, str]) -> str:
    """The calls to an endpoint, grouped by micro frontend and file."""

    return grouped(
        [
            (
                call.microfrontend,
                call.at.file,
                call.at.line,
                f'<span class="tag mono">{escape(call.method)}</span> '
                + (f'<span class="muted">{escape(call.client)}</span> ' if call.client else "")
                + place(call.screens, call.fragments),
            )
            for call in calls
        ],
        directories,
    )


def shared_endpoints(paths, data: dict, architecture: MicroFrontendArchitecture) -> str:
    """
    The shared routes, most called first, each in a block that
    opens: the methods and the callers in the closed row; the calls, by
    micro frontend and file, inside. The same design as the global-state
    slices.
    """

    wanted = set(paths)

    entries = [entry for entry in data["endpoints"] if entry["path"] in wanted]

    if not entries:
        return "—"

    directories = roots(architecture)

    calls: dict[str, list] = {}

    for item in architecture.api_calls:
        calls.setdefault(item.path, []).append(item)

    blocks = []

    for entry in entries:

        found = calls.get(entry["path"], [])

        blocks.append(
            '<details class="slice">'
            '<summary class="slice-head"><span class="caret">›</span>'
            f'<code><strong>{escape(entry["path"])}</strong></code>'
            f' <span class="muted mono">{escape(", ".join(entry["methods"]))}</span>'
            # Who hammers the route, already in the closed row.
            + f'<span class="slice-callers">{few(entry["callers"])}</span>'
            + mark(
                i18n.ref("endpoint.summary", mfes=len(entry["callers"]), n=len(found)),
                "span",
                ' class="muted slice-count"',
            )
            + "</summary>"
            '<dl class="slice-roles">'
            f"<div><dt>{mark('fact.callers')}</dt><dd>{names(entry['callers'])}</dd></div>"
            "</dl>"
            + _calls(found, directories)
            + "</details>"
        )

    return '<div class="slices">' + "".join(blocks) + "</div>"


def _access(access: str) -> str:
    """The read or write label, translated when there is a text for it."""

    key = f"value.{access}"

    if key in i18n.texts():
        return mark(key, "span", ' class="tag"')

    return f'<span class="tag">{escape(access)}</span>'


def _match(value: str) -> str:

    key = f"value.{value}"

    return mark(key) if key in i18n.texts() else escape(value)
