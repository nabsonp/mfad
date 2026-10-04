"""
Projeção dos artefatos para consumo da página.

O que a página precisa não é o `MicroFrontendArchitecture` inteiro: é uma
estrutura achatada, com identificadores curtos e as arestas já
individualizadas, para que o JavaScript não precise recalcular
nada em tempo de interação.
"""

from __future__ import annotations

from dataclasses import asdict

from damfe.domain import AntiPatternDetection, MicroFrontendArchitecture


#: Perspectivas do grafo. A ordem é a das abas na página.
RELATIONS = (
    ("fragment_import", "Composição"),
    ("navigation", "Navegação"),
    ("communication", "Comunicação"),
    ("shared_endpoint", "Backend"),
)

#: Relação DERIVADA: não é extraída do código, é calculada a
#: partir das chamadas externas. Dois micro frontends que consomem
#: o mesmo endpoint estão acoplados pelo backend, ainda que não se
#: conheçam. Por não ter direção, é desenhada sem seta.
DERIVED = "shared_endpoint"


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
        [(item.consumer, item.provider) for item in architecture.fragment_imports]
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

    for item in architecture.fragment_imports:

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
                "edge": edge_id(item.consumer, item.provider, "fragment_import"),
                "relation": "fragment_import",
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

    edges.extend(_shared_endpoints(architecture))

    for item in architecture.communications:

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
                "detail": f"mecanismo: {item.mechanism}",
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
                    "detail": "montado pelo orquestrador",
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


def _shared_endpoints(architecture: MicroFrontendArchitecture) -> list[dict]:
    """
    Pares de micro frontends que consomem o mesmo endpoint.

    Emitidos nos dois sentidos para que o desenho ligue o par
    independentemente de qual lado for consultado; a ausência de
    seta é o que comunica que a relação não tem direção.
    """

    callers: dict[str, set[str]] = {}

    for item in architecture.api_calls:
        callers.setdefault(item.path, set()).add(item.microfrontend)

    edges: list[dict] = []

    for path, consumers in sorted(callers.items()):

        if len(consumers) < 2:
            continue

        ordered = sorted(consumers)

        for source in ordered:
            for target in ordered:

                if source == target:
                    continue

                edges.append(
                    {
                        "edge": edge_id(source, target, DERIVED),
                        "relation": DERIVED,
                        "source": source,
                        "target": target,
                        "label": path,
                        "file": None,
                        "line": 0,
                        "code": None,
                        "detail": "mesmo endpoint consumido pelos dois",
                    }
                )

    return edges


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
