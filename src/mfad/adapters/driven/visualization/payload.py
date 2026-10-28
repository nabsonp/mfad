"""
Projection of the artifacts for the page to consume.

What the page needs is not the whole `MicroFrontendArchitecture`: it
is a flattened structure, with short identifiers and the edges already
individualized, so the JavaScript does not need to recompute anything
at interaction time.
"""

from __future__ import annotations

import re
from dataclasses import asdict

from mfad.adapters.driven import i18n
from mfad.domain import AntiPatternDetection, MicroFrontendArchitecture, Placement


#: Relations between pairs of micro frontends, in tab order.
RELATIONS = (
    ("composition", "Composition"),
    ("navigation", "Navigation"),
    ("communication", "Communication"),
)



def build(
    architecture: MicroFrontendArchitecture,
    detections: list[AntiPatternDetection],
) -> dict:

    degrees = _degrees(architecture)

    counts = _detection_counts(detections)

    return {
        "project": architecture.project,
        "microfrontends": [
            _microfrontend(item, degrees, counts)
            for item in architecture.microfrontends
        ],
        "edges": _edges(architecture),
        "api_calls": _api_calls(architecture),
        "endpoints": _endpoints(architecture),
        "slices": _slices(architecture),
        "screens": _screens(architecture),
        "screen_edges": _screen_edges(architecture),
        "detections": [
            _detection(index, item)
            for index, item in enumerate(detections)
        ],
    }


def short(identifier: str) -> str:

    return identifier.rpartition("/")[2] or identifier


def edge_id(source: str, target: str, relation: str) -> str:
    """Stable identifier of an aggregated edge in the drawing."""

    return f"{_slug(source)}--{_slug(target)}--{relation}"


def _slug(value: str) -> str:

    return "".join(
        character if character.isalnum() else "_" for character in value
    )


def _degrees(architecture: MicroFrontendArchitecture) -> dict[str, dict[str, int]]:
    """
    Distinct incoming and outgoing neighbors, summed over the extracted
    relations. It counts neighbors, not edges: two fragments from the
    same provider are one dependency, not two.
    """

    outgoing: dict[str, set[str]] = {}
    incoming: dict[str, set[str]] = {}

    pairs = (
        [(item.consumer, item.provider) for item in architecture.compositions]
        + [(item.source, item.target) for item in architecture.navigations]
        + [(item.source, item.target) for item in architecture.communications]
    )

    for source, target in pairs:

        if source == target:
            continue

        outgoing.setdefault(source, set()).add(target)
        incoming.setdefault(target, set()).add(source)

    return {
        item.id: {
            "out": len(outgoing.get(item.id, ())),
            "in": len(incoming.get(item.id, ())),
        }
        for item in architecture.microfrontends
    }


def _detection_counts(
    detections: list[AntiPatternDetection],
) -> dict[str, int]:

    counts: dict[str, int] = {}

    for detection in detections:
        for subject in detection.subjects:
            counts[subject] = counts.get(subject, 0) + 1

    return counts


def _microfrontend(item, degrees: dict, counts: dict) -> dict:

    return {
        "degree": degrees.get(item.id, {"in": 0, "out": 0}),
        "detections": counts.get(item.id, 0),
        "id": item.id,
        "short": short(item.id),
        "role": item.role,
        "reexports": item.metadata.get("reexports", 0),
        "directory": item.directory,
        "entrypoint": item.entrypoint,
        "routes": item.routes,
        "size": {
            "files": item.size.files,
            "lines": item.size.lines,
            "code_lines": item.size.code_lines,
        },
        "screens": [
            {
                "component": screen.component,
                "route": screen.route,
                "expression": screen.route_expression,
                "file": screen.file,
                "line": screen.line,
            }
            for screen in item.screens
        ],
        "fragments": [
            {
                "name": fragment.name,
                "file": fragment.file,
                "line": fragment.line,
            }
            for fragment in item.fragments
        ],
    }


def _edges(architecture: MicroFrontendArchitecture) -> list[dict]:
    """
    One entry per concrete relation, not per pair of nodes.

    The drawing aggregates by `edge_id`; the side panel needs the
    individual items, with file, line and the code snippet.
    """

    edges: list[dict] = []

    for item in architecture.compositions:

        renders = [
            {
                "file": render.file,
                "line": render.line,
                "props": render.props,
                "screens": [short(name) for name in render.screens],
            }
            for render in item.renders
        ]

        edges.append(
            {
                "edge": edge_id(item.consumer, item.provider, "composition"),
                "relation": "composition",
                "source": item.consumer,
                "target": item.provider,
                "label": item.fragment,
                "file": item.imported_at.file,
                "line": item.imported_at.line,
                "code": item.imported_at.code,
                "renders": renders,
            }
        )

    for item in architecture.navigations:

        edges.append(
            {
                "edge": edge_id(item.source, item.target, "navigation"),
                "relation": "navigation",
                "source": item.source,
                "target": item.target,
                "label": item.resolved_url or item.expression,
                "file": item.at.file,
                "line": item.at.line,
                "code": item.at.code,
                "detail": f"{item.expression} ⇒ {item.resolved_url} ({item.match})",
            }
        )

    edges.extend(_mounts(architecture))

    for item in architecture.communications:

        # Global state is not a message between a pair: it is a slice that
        # several touch. As pairs, each slice with N readers became N²
        # edges (4,436 in udistrital), and the graph was unreadable.
        # It shows up in its own view, built from the accesses.
        if not item.directed:
            continue

        first = (item.produced_at or item.consumed_at or [None])[0]

        edges.append(
            {
                "edge": edge_id(item.source, item.target, "communication"),
                "relation": "communication",
                "source": item.source,
                "target": item.target,
                "label": item.channel,
                "file": first.file if first else None,
                "line": first.line if first else 0,
                "code": first.code if first else None,
                "detail": i18n.ref("detail.mechanism", mechanism=item.mechanism),
            }
        )

    return edges


def _mounts(architecture: MicroFrontendArchitecture) -> list[dict]:
    """
    The shell mounting each application it registered.

    Without this edge the graph shows loose micro frontends, with
    nothing explaining how they reach the page, and the missing relation
    is the one that defines the system. A navbar mounted on every URL is
    not imported by anyone: whoever puts it there is the shell, and it is
    this edge, not an invented import between pairs, that says so.
    """

    known = {item.id for item in architecture.microfrontends}

    edges: list[dict] = []

    for item in architecture.microfrontends:

        for mounted in item.mounts:

            if mounted not in known:
                continue

            edges.append(
                {
                    "edge": edge_id(item.id, mounted, "mount"),
                    "relation": "mount",
                    "source": item.id,
                    "target": mounted,
                    "label": "registerApplication",
                    "file": item.entrypoint or None,
                    "line": 0,
                    "code": None,
                    "detail": i18n.ref("detail.mounted"),
                }
            )

    return edges


def _api_calls(architecture: MicroFrontendArchitecture) -> list[dict]:

    return [
        {
            "microfrontend": item.microfrontend,
            "method": item.method,
            "path": item.path,
            "match": item.match,
            "client": item.client,
            "screens": item.screens,
            "file": item.at.file,
            "line": item.at.line,
            "code": item.at.code,
        }
        for item in architecture.api_calls
    ]


def _endpoints(architecture: MicroFrontendArchitecture) -> list[dict]:
    """
    Endpoints aggregated by path, with who consumes them.

    Backend coupling shows up here: an endpoint called by more than
    one micro frontend is a shared dependency that none of the other
    three graphs shows.
    """

    grouped: dict[str, dict] = {}

    for item in architecture.api_calls:

        entry = grouped.setdefault(
            item.path,
            {"path": item.path, "methods": set(), "callers": set()},
        )

        entry["methods"].add(item.method)
        entry["callers"].add(item.microfrontend)

    return sorted(
        (
            {
                "path": entry["path"],
                "methods": sorted(entry["methods"]),
                "callers": sorted(entry["callers"]),
            }
            for entry in grouped.values()
        ),
        key=lambda entry: (-len(entry["callers"]), entry["path"]),
    )


# ----------------------------------------------------------------------
# Global state
# ----------------------------------------------------------------------


def _slices(architecture: MicroFrontendArchitecture) -> list[dict]:
    """
    Global-state slices touched by more than one micro frontend.

    The slice is the node, and each micro frontend that reads or writes
    it links to it. It is the same coupling as the pairwise state
    edges, without the Cartesian product.
    """

    grouped: dict[tuple[str, str], list] = {}

    for item in architecture.state_accesses:
        grouped.setdefault((item.library, item.path), []).append(item)

    slices = []

    for (library, path), accesses in sorted(grouped.items()):

        owners = sorted({item.microfrontend for item in accesses})

        if len(owners) < 2:
            continue

        slices.append(
            {
                "id": f"{library}:{path}",
                "library": library,
                "path": path,
                "microfrontends": owners,
                "accesses": [
                    {
                        "microfrontend": item.microfrontend,
                        "access": item.access,
                        "file": item.at.file,
                        "line": item.at.line,
                        "code": item.at.code,
                    }
                    for item in sorted(
                        accesses,
                        key=lambda item: (item.microfrontend, item.at.file, item.at.line),
                    )
                ],
            }
        )

    return slices


# ----------------------------------------------------------------------
# Screens
# ----------------------------------------------------------------------


def _screens(architecture: MicroFrontendArchitecture) -> dict[str, dict]:
    """Screens and fragments by identifier, for the panel and the drawing."""

    found: dict[str, dict] = {}

    for microfrontend in architecture.microfrontends:

        for screen in microfrontend.screens:
            found[screen.id] = {
                "id": screen.id,
                "kind": "screen",
                "microfrontend": microfrontend.id,
                "name": screen.component,
                "route": screen.route,
                "file": screen.file,
                "line": screen.line,
            }

        for fragment in microfrontend.fragments:
            found[fragment.id] = {
                "id": fragment.id,
                "kind": "fragment",
                "microfrontend": microfrontend.id,
                "name": fragment.name,
                "route": None,
                "file": fragment.file,
                "line": fragment.line,
            }

    return found


def _screen_edges(architecture: MicroFrontendArchitecture) -> list[dict]:
    """
    The relations between micro frontends at screen level.

    - composition: the screen that instantiates -> the provider's fragment;
    - communication: the screen of the publishing end -> that of the subscribing one;
    - navigation: the screen navigated from -> the screen whose route receives.

    When the code is not reached by any screen (the orchestrator, a
    utility mounted separately), the end is the micro frontend itself:
    the relation exists, it just has no place in the interface.
    """

    known = {item.id for item in architecture.microfrontends}

    screens = _screens(architecture)

    grouped: dict[tuple[str, str, str], dict] = {}

    def add(sources, targets, relation, label, occurrence) -> None:

        for source in sources:
            for target in targets:

                if source == target:
                    continue

                entry = grouped.setdefault(
                    (source, target, relation),
                    {
                        "id": f"{_slug(source)}--{_slug(target)}--{relation}",
                        "relation": relation,
                        "source": source,
                        "target": target,
                        "labels": [],
                        "items": [],
                    },
                )

                if label and label not in entry["labels"]:
                    entry["labels"].append(label)

                if occurrence not in entry["items"]:
                    entry["items"].append(occurrence)

    def places(placement: Placement, owner: str) -> list[str]:

        found = [
            item
            for item in placement.screens + placement.fragments
            if item in screens and screens[item]["microfrontend"] == owner
        ]

        return found or ([owner] if owner in known else [])

    for item in architecture.compositions:

        fragment = f"{item.provider}#{item.fragment}"

        target = [fragment] if fragment in screens else [item.provider]

        renders = item.renders or []

        if not renders:
            add(
                [item.consumer], target, "composition", item.fragment,
                _occurrence(item.imported_at.file, item.imported_at.line, item.imported_at.code, ""),
            )

        for render in renders:
            add(
                places(Placement(screens=render.screens, fragments=render.fragments), item.consumer),
                target,
                "composition",
                item.fragment,
                _occurrence(render.file, render.line, None, i18n.ref("detail.rendered_here")),
            )

    for item in architecture.communications:

        if not item.directed:
            continue

        first = (item.produced_at or item.consumed_at or [None])[0]

        add(
            places(item.produced_on, item.source),
            places(item.consumed_on, item.target),
            "communication",
            item.channel,
            _occurrence(
                first.file if first else None,
                first.line if first else 0,
                first.code if first else None,
                f"{item.mechanism} · {item.channel}",
            ),
        )

    for item in architecture.navigations:

        landing = arrival(architecture, item.target, item.resolved_url)

        add(
            places(item.on, item.source),
            [landing] if landing else [item.target],
            "navigation",
            item.resolved_url or item.expression,
            _occurrence(item.at.file, item.at.line, item.at.code, item.expression),
        )

    return sorted(grouped.values(), key=lambda entry: entry["id"])


def _occurrence(file, line, code, detail) -> dict:

    return {"file": file, "line": line, "code": code, "detail": detail}


#: Route segment that accepts any value.
_WILDCARD = re.compile(r"^(:.+|\*|\{.*\}|\[.*\])$")


def arrival(
    architecture: MicroFrontendArchitecture,
    microfrontend: str,
    url: str | None,
) -> str | None:
    """
    The screen of the micro frontend whose route receives the URL.

    The most specific route wins: `/loja/produto/:id` before
    `/loja/*`. A variable segment (`:id`, `*`, `{param}`) matches any
    value; a trailing `*` matches the rest of the path.
    """

    owner = architecture.microfrontend(microfrontend)

    if owner is None or not url:
        return None

    wanted = [part for part in url.split("?")[0].split("/") if part]

    best: tuple[int, str] | None = None

    for screen in owner.screens:

        if screen.route is None:
            continue

        pattern = [part for part in screen.route.split("/") if part]

        score = _route_score(pattern, wanted)

        if score is not None and (best is None or score > best[0]):
            best = (score, screen.id)

    return best[1] if best else None


def _route_score(pattern: list[str], wanted: list[str]) -> int | None:

    literal = 0

    for index, part in enumerate(pattern):

        if part == "*" and index == len(pattern) - 1:
            return literal

        if index >= len(wanted):
            return None

        if _WILDCARD.match(part) or _WILDCARD.match(wanted[index]):
            continue

        if part != wanted[index]:
            return None

        literal += 2

    return literal + 1 if len(pattern) == len(wanted) else None


def _detection(index: int, item: AntiPatternDetection) -> dict:

    payload = asdict(item)

    payload["index"] = index

    payload["edges"] = [
        edge_id(source, target, relation)
        for source, target in item.metadata.get("edges", [])
        for relation in _relations_of(item)
    ]

    payload["pairs"] = item.metadata.get("edges", [])

    return payload


def _relations_of(item: AntiPatternDetection) -> list[str]:
    """
    Which relations the detection involves.

    When the rule declares one (`cyclic-dependency` does), only that
    one is highlighted. When it does not, the highlight reaches all
    three; that is the conservative behavior: better to highlight too
    much than to hide the evidence.
    """

    relation = item.metadata.get("relation")

    if relation:
        return [relation]

    return [key for key, _ in RELATIONS]
