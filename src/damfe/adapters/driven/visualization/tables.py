"""
As tabelas de cada aba do cabeçalho: tudo o que os números contam.

O mapa responde quem se liga a quem; a tabela responde quantos,
quais e onde, linha a linha, com o arquivo e a linha de cada coisa.
Cada número do cabeçalho leva à lista que o soma — o número que não
se pode abrir pede confiança, o que se pode abrir se confere.

A tabela mostra poucas colunas, as que identificam o item; o resto
fica num detalhe que a linha abre ao ser clicada. Com todas as
colunas lado a lado, a tabela não cabia na tela e era preciso rolar
para o lado para ler uma linha só. O detalhe traz também o atalho
para o item no mapa.

As tabelas saem prontas do Python, como o resto da página. O script
só filtra, ordena e abre as linhas que já estão lá.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field

from damfe.adapters.driven import i18n
from damfe.adapters.driven.i18n import mark, marker
from damfe.adapters.driven.visualization import payload
from damfe.domain import MicroFrontendArchitecture


@dataclass
class Column:

    #: chave do cabeçalho em `texts.json`
    key: str

    numeric: bool = False

    #: na linha; as demais vão para o detalhe
    summary: bool = True

    #: no detalhe, ocupa a largura toda: listas de caminhos não cabem
    #: numa coluna da grade
    wide: bool = False


@dataclass
class Row:

    cells: list[str]

    #: o atalho para o item no mapa: (chave do texto do botão, atributos `data-go-*`)
    go: tuple[str, dict[str, str]] | None = None

    #: `data-key` são as chaves da linha, separadas por espaço: os
    #: links da barra lateral a acham por elas
    attrs: dict[str, str] = field(default_factory=dict)

    #: campos só desta linha, antes dos das colunas: o rótulo (já
    #: marcado para tradução), o valor e, opcional, se ocupa a largura
    #: toda; para tabela cujos itens não têm todos os mesmos campos,
    #: como as detecções
    fields: list[tuple] = field(default_factory=list)

    #: botão no lugar do atalho `go`, para a ação que não é ir a uma aba
    action: str = ""


def escape(value) -> str:
    return html.escape(str(value), quote=True)


def short(identifier: str) -> str:
    return escape(payload.short(identifier))


#: A cor de cada anti-padrão, fixa: o mesmo nome tem a mesma cor em
#: qualquer sistema. As de grafo têm a cor da relação que as mostra
#: (estado global violeta, backend âmbar).
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
    """A cor do anti-padrão; um que não está na lista ganha uma pelo nome."""

    return COLORS.get(name) or PALETTE[sum(map(ord, name)) % len(PALETTE)]


def anti_pattern(name: str) -> str:
    return f'<span class="ap-tag ap-{color_of(name)}">{escape(name)}</span>'


def names(identifiers) -> str:
    return ", ".join(short(item) for item in identifiers) or "—"


def few(identifiers, limit: int = 3) -> str:
    """
    Os primeiros nomes e quantos faltam, para a linha caber na tela;
    a lista inteira vai para o detalhe.
    """

    identifiers = list(identifiers)

    if len(identifiers) <= limit:
        return names(identifiers)

    return names(identifiers[:limit]) + f' <span class="muted">+{len(identifiers) - limit}</span>'


def screen_names(identifiers) -> str:
    """`mfe#Tela` vira `Tela`: a coluna já diz de que micro frontend é."""

    return ", ".join(escape(item.partition("#")[2] or item) for item in identifiers) or "—"


def where(file: str | None, line: int) -> str:

    if not file:
        return "—"

    return f"<code>{escape(file)}:{line}</code>" if line else f"<code>{escape(file)}</code>"


def place(screens: list[str], fragments: list[str]) -> str:
    """
    Onde, na interface, o código roda: as telas e os fragmentos que o
    alcançam, ou fora de tela quando nenhum alcança.
    """

    parts = []

    if screens:
        parts.append(mark(i18n.ref("place.screens", names=", ".join(screens))))

    if fragments:
        parts.append(mark(i18n.ref("place.fragments", names=", ".join(fragments))))

    return " · ".join(parts) or mark("screen.outside", "span", ' class="muted"')


def grouped(entries: list[tuple[str, str | None, int, str]], roots: dict[str, str]) -> str:
    """
    Localizações agrupadas por micro frontend e, dentro dele, por arquivo.

    Cada entrada é `(micro frontend, arquivo, linha, etiqueta)`; a
    etiqueta diz o que acontece naquela linha (lê, importa, o método).
    O micro frontend aparece uma vez, como título do grupo, e o
    diretório dele sai do caminho. Cada arquivo aparece uma vez, com
    as linhas dele ao lado: o mesmo arquivo que importa e instancia um
    fragmento é uma linha só, não duas separadas por outras. O caminho
    inteiro fica no `title`.
    """

    if not entries:
        return "—"

    # Por arquivo, as linhas de cada etiqueta juntas: três chamadas
    # iguais no mesmo arquivo são uma etiqueta com três linhas, não a
    # etiqueta repetida três vezes.
    groups: dict[str, dict[str | None, dict[str, list[int]]]] = {}

    for owner, file, line, label in entries:

        lines = groups.setdefault(owner, {}).setdefault(file, {}).setdefault(label, [])

        if line and line not in lines:
            lines.append(line)

    def hits(labels: dict[str, list[int]]) -> str:

        # O número logo depois do arquivo, como `arquivo:linha`; o que
        # acontece ali vem depois.
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
    """O micro frontend do arquivo: o de diretório mais longo que o contém."""

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
    A tabela com o filtro e a contagem em cima.

    Cada item são duas linhas: a de resumo, com as colunas marcadas
    `summary`, e a de detalhe, escondida, com todas as colunas e o
    atalho para o mapa. Coluna numérica é ordenada pelo número, não
    pelo texto: "10" depois de "9".
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
            # Célula `None`: o campo não se aplica a esta linha.
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
# Uma tabela por aba
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
            # O que o micro frontend define, com a contagem no rótulo.
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

    # Só a tela que participa de alguma relação está na aba Telas; as
    # outras levam ao micro frontend.
    related = {edge["source"] for edge in data["screen_edges"]} | {
        edge["target"] for edge in data["screen_edges"]
    }

    # Os fragmentos de outros micro frontends que cada tela instancia:
    # é o que a tela mostra que não é dela.
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
    Fragmentos e composições numa tabela só: uma linha por fragmento.

    A composição é o fragmento visto de quem o monta. Em tabelas
    separadas, saber em que telas um fragmento aparece pedia cruzar
    as duas; aqui a linha já diz, e o detalhe traz cada composição —
    o consumidor, onde importa e onde instancia.
    """

    by_fragment: dict[tuple[str, str], list] = {}

    for item in architecture.compositions:
        by_fragment.setdefault((item.provider, item.fragment), []).append(item)

    exposed = [
        (microfrontend.id, fragment.name, fragment.file, fragment.line)
        for microfrontend in architecture.microfrontends
        for fragment in microfrontend.fragments
    ]

    # Fragmento composto que a extração não listou como exposto entra
    # também: nenhuma composição pode sumir da tabela.
    known = {(provider, name) for provider, name, _, _ in exposed}

    exposed += [
        (provider, name, None, 0)
        for provider, name in sorted(by_fragment)
        if (provider, name) not in known
    ]

    columns = [
        Column("col.fragment"),
        Column("col.provider"),
        # Quem monta é uma lista que cresce com o reúso: na linha fica a
        # contagem, que ordena; os nomes vão para o detalhe.
        Column("col.compositions", True),
        Column("col.mounted_on"),
        # Quem monta já é o título de cada grupo do "composto em".
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
    """O atalho para a aresta: a aba da relação, com o painel dela aberto."""

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
    """Só as que têm sentido: o estado global está na aba de fatias."""

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
    As fatias do estado global, cada uma com quem lê, quem grava e
    onde, agrupado por micro frontend e arquivo.

    Fica no detalhe da detecção de estado global: é a evidência dela,
    e numa aba à parte repetia o que a detecção já diz.
    """

    if not entries:
        return "—"

    blocks = []

    for entry in entries:

        readers = sorted({item["microfrontend"] for item in entry["accesses"] if item["access"] != "write"})
        writers = sorted({item["microfrontend"] for item in entry["accesses"] if item["access"] == "write"})

        # Cada fatia fecha: com dezenas de acessos, abertas todas
        # empurravam o porquê da detecção para longe. A linha fechada
        # já diz quantos micro frontends e quantos acessos há nela.
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
    """Os endpoints, os compartilhados primeiro: são o acoplamento por backend."""

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
                # Só o compartilhado está na aba Backend.
                ("table.show_endpoint", {"kind": "slot", "target": entry["path"], "view": "backend"})
                if shared
                else to_map(entry["callers"][0]),
                attrs={"data-key": entry["path"]},
            )
        )

    return table(columns, rows)


def _calls(calls: list, directories: dict[str, str]) -> str:
    """As chamadas a um endpoint, agrupadas por micro frontend e arquivo."""

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
    As rotas compartilhadas, mais chamadas primeiro, cada uma num bloco
    que abre: os métodos e quem chama na linha fechada; as chamadas, por micro frontend e
    arquivo, dentro. O mesmo desenho das fatias do estado global.
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
            # Quem martela a rota, já na linha fechada.
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
    """A etiqueta da leitura ou escrita, traduzida quando há texto para ela."""

    key = f"value.{access}"

    if key in i18n.texts():
        return mark(key, "span", ' class="tag"')

    return f'<span class="tag">{escape(access)}</span>'


def _match(value: str) -> str:

    key = f"value.{value}"

    return mark(key) if key in i18n.texts() else escape(value)
