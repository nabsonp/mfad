"""
Projeção dos artefatos para consumo da página.

O que a página precisa não é o `MicroFrontendArchitecture` inteiro: é uma
estrutura achatada, com identificadores curtos e as arestas já
individualizadas, para que o JavaScript não precise recalcular
nada em tempo de interação.
"""

from __future__ import annotations

import re
from dataclasses import asdict

from mfad.adapters.driven import i18n
from mfad.domain import AntiPatternDetection, MicroFrontendArchitecture, Placement


#: Relações entre pares de micro frontends, na ordem das abas.
RELATIONS = (
    ("composition", "Composição"),
    ("navigation", "Navegação"),
    ("communication", "Comunicação"),
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
    """Identificador estável de uma aresta agregada no desenho."""

    return f"{_slug(source)}--{_slug(target)}--{relation}"


def _slug(value: str) -> str:

    return "".join(
        character if character.isalnum() else "_" for character in value
    )


def _degrees(architecture: MicroFrontendArchitecture) -> dict[str, dict[str, int]]:
    """
    Vizinhos distintos de entrada e de saída, somadas as relações
    extraídas. Conta vizinhos, não arestas: dois fragmentos do
    mesmo provedor são uma dependência, não duas.
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
    Uma entrada por relação concreta, não por par de nós.

    O desenho agrega por `edge_id`; o painel lateral precisa dos
    itens individuais, com arquivo, linha e o trecho de código.
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

        # Estado global não é mensagem entre um par: é uma fatia que
        # vários tocam. Como par, cada fatia com N leitores virava N²
        # arestas — no udistrital, 4.436 —, e o grafo ficava ilegível.
        # Ela aparece na sua própria visão, a partir dos acessos.
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
    O shell montando cada aplicação que registrou.

    Sem esta aresta o grafo mostra micro frontends soltos, sem nada
    explicando como chegam à página — e a relação que falta é a que
    define o sistema. Um navbar montado em toda URL não é importado
    por ninguém: quem o coloca lá é o shell, e é esta aresta, não um
    import inventado entre pares, que diz isso.
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
    Endpoints agregados por caminho, com quem os consome.

    O acoplamento por backend aparece aqui: um endpoint chamado
    por mais de um micro frontend é dependência compartilhada que
    nenhum dos outros três grafos mostra.
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
# Estado global
# ----------------------------------------------------------------------


def _slices(architecture: MicroFrontendArchitecture) -> list[dict]:
    """
    Fatias do estado global tocadas por mais de um micro frontend.

    A fatia é o nó, e cada micro frontend que a lê ou grava se liga
    a ela. É o mesmo acoplamento das arestas de estado entre pares,
    sem o produto cartesiano.
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
# Telas
# ----------------------------------------------------------------------


def _screens(architecture: MicroFrontendArchitecture) -> dict[str, dict]:
    """Telas e fragmentos por identificador, para o painel e o desenho."""

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
    As relações entre micro frontends no nível de tela.

    - composição: a tela que instancia → o fragmento do provedor;
    - comunicação: a tela da ponta que publica → a da que assina;
    - navegação: a tela de onde se navega → a tela cuja rota recebe.

    Quando o código não é alcançado por tela nenhuma — o orquestrador,
    um utilitário montado à parte —, a ponta é o próprio micro
    frontend: a relação existe, só não tem lugar na interface.
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


#: Segmento de rota que aceita qualquer valor.
_WILDCARD = re.compile(r"^(:.+|\*|\{.*\}|\[.*\])$")


def arrival(
    architecture: MicroFrontendArchitecture,
    microfrontend: str,
    url: str | None,
) -> str | None:
    """
    A tela do micro frontend cuja rota recebe a URL.

    A rota mais específica vence: `/loja/produto/:id` antes de
    `/loja/*`. Segmento variável (`:id`, `*`, `{param}`) casa com
    qualquer valor; `*` no fim casa com o resto do caminho.
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
    Quais relações a detecção envolve.

    Quando a regra declara uma (`cyclic-dependency` declara), só
    ela é destacada. Quando não declara, o destaque alcança as
    três — é o comportamento conservador: melhor destacar demais
    que esconder a evidência.
    """

    relation = item.metadata.get("relation")

    if relation:
        return [relation]

    return [key for key, _ in RELATIONS]
