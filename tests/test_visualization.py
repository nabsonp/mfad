"""
A página: visões por pergunta, estado global como fatia e telas.

O desenho é gerado em Python e tem de ser o mesmo a cada execução;
os testes olham o que vai para a página, não pixels.
"""

import re

from mfad.adapters.driven.visualization import layout, payload, views
from mfad.adapters.driven.visualization.html import HtmlRenderer
from mfad.domain import (
    Communication,
    Composition,
    Fragment,
    MicroFrontend,
    MicroFrontendArchitecture,
    Navigation,
    Placement,
    RenderLocation,
    Screen,
    SourceLocation,
    StateAccess,
)


def at(file: str, line: int = 1) -> SourceLocation:
    return SourceLocation(file=file, line=line, code="x")


def architecture() -> MicroFrontendArchitecture:
    """Loja com catálogo, carrinho e conta, montados por um orquestrador."""

    return MicroFrontendArchitecture(
        project="loja",
        microfrontends=[
            MicroFrontend(id="shell", role="shell", mounts=["catalog", "cart", "account"]),
            MicroFrontend(
                id="catalog",
                screens=[
                    Screen(component="Products", microfrontend="catalog", route="/catalog", file="catalog/Products.js"),
                    Screen(component="Product", microfrontend="catalog", route="/catalog/:id", file="catalog/Product.js"),
                ],
            ),
            MicroFrontend(
                id="cart",
                screens=[Screen(component="Cart", microfrontend="cart", route="/cart", file="cart/Cart.js")],
                fragments=[Fragment(name="MiniCart", microfrontend="cart", file="cart/MiniCart.js")],
            ),
            MicroFrontend(
                id="account",
                screens=[Screen(component="Profile", microfrontend="account", route="/account", file="account/Profile.js")],
            ),
        ],
        compositions=[
            Composition(
                consumer="catalog",
                provider="cart",
                fragment="MiniCart",
                local_name="MiniCart",
                imported_at=at("catalog/Product.js"),
                renders=[RenderLocation(file="catalog/Product.js", line=9, screens=["catalog#Product"])],
            )
        ],
        navigations=[
            Navigation(
                source="cart",
                target="catalog",
                expression='"/catalog/42"',
                resolved_url="/catalog/42",
                match="exact",
                at=at("cart/Cart.js", 12),
                on=Placement(screens=["cart#Cart"]),
            )
        ],
        communications=[
            Communication(
                source="catalog",
                target="cart",
                mechanism="CustomEvent",
                channel="cart:add",
                produced_at=[at("catalog/Product.js", 20)],
                consumed_at=[at("cart/store.js", 3)],
                produced_on=Placement(screens=["catalog#Product"]),
                # O assinante está num módulo que nenhuma tela alcança.
                consumed_on=Placement(),
            ),
            # Os pares que a reconstrução deriva do estado global.
            Communication(source="catalog", target="cart", mechanism="global-state",
                          channel="localStorage:token", directed=False),
            Communication(source="cart", target="catalog", mechanism="global-state",
                          channel="localStorage:token", directed=False),
        ],
        state_accesses=[
            StateAccess(microfrontend="catalog", library="localStorage", path="token", at=at("catalog/a.js"), access="read"),
            StateAccess(microfrontend="cart", library="localStorage", path="token", at=at("cart/a.js"), access="read"),
            StateAccess(microfrontend="account", library="localStorage", path="token", at=at("account/a.js"), access="write"),
            StateAccess(microfrontend="account", library="localStorage", path="theme", at=at("account/b.js"), access="write"),
        ],
    )


def test_shared_state_is_a_slice_not_a_pair_per_reader():
    """Uma fatia com N participantes é um nó com N ligações, não N² arestas."""

    data = payload.build(architecture(), [])

    assert not [edge for edge in data["edges"] if edge["label"] == "localStorage:token"]

    [slice_] = data["slices"]

    assert slice_["id"] == "localStorage:token"
    assert slice_["microfrontends"] == ["account", "cart", "catalog"]

    # `theme` só é tocada por um: não é acoplamento.
    assert "localStorage:theme" not in [item["id"] for item in data["slices"]]


def test_relations_at_screen_level():

    edges = {
        (edge["relation"], edge["source"], edge["target"]): edge
        for edge in payload.build(architecture(), [])["screen_edges"]
    }

    # A tela que instancia → o fragmento do provedor.
    assert ("composition", "catalog#Product", "cart#MiniCart") in edges

    # Ponta em código que nenhuma tela alcança fica no micro frontend.
    assert ("communication", "catalog#Product", "cart") in edges

    # A navegação chega à tela cuja rota recebe a URL: `/catalog/:id`
    # é mais específica que `/catalog` para `/catalog/42`.
    assert ("navigation", "cart#Cart", "catalog#Product") in edges


def test_force_layout_has_no_overlap_and_is_deterministic():

    sizes = {f"mfe-{index}": (140 + index * 3, layout.NODE_HEIGHT) for index in range(30)}

    # Anel com cordas: os 25 primeiros ligados, sem laço.
    edges = [(f"mfe-{index}", f"mfe-{(index + step) % 25}", 1.0) for index in range(25) for step in (1, 5)]

    first = layout.force(sizes, edges)
    second = layout.force(sizes, edges)

    assert first == second

    boxes, isolated, _, _ = first

    # Os cinco sem aresta ficam à parte, não espalhados entre os ligados.
    assert isolated == ["mfe-25", "mfe-26", "mfe-27", "mfe-28", "mfe-29"]

    placed = sorted(boxes.items())

    for index, (_, a) in enumerate(placed):
        for _, b in placed[index + 1:]:
            assert abs(a.x - b.x) >= (a.w + b.w) / 2 or abs(a.y - b.y) >= (a.h + b.h) / 2


def test_screen_groups_flow_left_to_right():
    """Quem publica fica à esquerda de quem recebe."""

    groups = [
        layout.Group(id=name, title_width=80, members=[(f"{name}#Screen", 120)])
        for name in ("a", "b", "c")
    ]

    _, frames, _, _ = layout.clusters(
        groups,
        [("a#Screen", "b#Screen"), ("b#Screen", "c#Screen")],
        {f"{name}#Screen": name for name in ("a", "b", "c")},
    )

    assert frames["a"].x < frames["b"].x < frames["c"].x


def test_page_has_one_view_per_question():

    page = HtmlRenderer().render(architecture(), [])

    # Um card por grafo no dashboard, todos à vista: sem abas.
    cards = re.findall(r'<section class="block view" data-view="([^"]+)"', page)

    assert cards == ["overview", "composition", "navigation", "communication", "state", "screens"]
    assert 'class="tab"' not in page and 'data-zoom="expand"' in page

    # Sem endpoint compartilhado, sem card de backend.
    assert 'data-view="backend"' not in page

    # Um recorte da visão de telas por micro frontend envolvido.
    assert sorted(re.findall(r'<template data-variant="([^"]+)"', page)) == ["cart", "catalog"]


def test_metrics_count_messages_and_slices_not_state_pairs():

    page = HtmlRenderer().render(architecture(), [])

    assert re.search(r"<strong>1</strong><span[^>]*>comunicações</span>", page)
    # O estado global não tem aba: as fatias estão na detecção.
    assert 'data-page="slices"' not in page


def test_pair_view_draws_each_direction_with_its_own_arrow():
    """Ida e volta são dois arcos com uma seta cada, não uma linha de duas pontas."""

    data = payload.build(architecture(), [])

    data["edges"].append(
        {**data["edges"][0], "source": "cart", "target": "catalog", "edge": "volta"}
    )

    view = views.pairs_view("x", "x", data, ["composition"], {}, keep_isolated=False)

    groups = re.findall(r'<g class="edge-group"[^>]*>.*?</g>', view.svg)

    assert len(groups) == 2

    for group in groups:
        assert "marker-end" in group and "marker-start" not in group

    paths = [re.search(r'class="edge composition" d="([^"]+)"', group).group(1) for group in groups]

    assert paths[0] != paths[1]


def test_legend_says_what_the_arrow_means():
    """Sem a frase, `A → B` na composição não diz quem exibe quem."""

    page = HtmlRenderer().render(architecture(), [])

    text = re.sub(r"<[^>]+>", "", page)

    assert "A → B: A exibe um fragmento de B" in text
    assert "A → B: A leva o usuário para uma rota de B" in text
    assert "A → B: a tela A exibe o fragmento B" in text

    # E o tooltip de cada aresta diz com os nomes.
    assert re.search(r"<title[^>]*>catalog exibe um fragmento de cart", page)


def test_every_text_has_both_languages_with_the_same_slots():
    """Uma tradução que esquece `{n}` mostraria a frase sem o número."""

    from mfad.adapters.driven import i18n

    for key, entry in i18n.texts().items():

        versions = {language: entry.get(language) for language in i18n.LANGUAGES}

        assert all(versions.values()), f"{key} sem um dos idiomas"

        def slots(value):
            texts = value.values() if isinstance(value, dict) else [value]
            return {slot for text in texts for slot in re.findall(r"\{(\w+)\}", text)}

        assert slots(versions["pt"]) == slots(versions["en"]), key


def test_every_marked_text_on_the_page_exists():

    from mfad.adapters.driven import i18n

    page = HtmlRenderer().render(architecture(), [])

    keys = set(re.findall(r'data-t="([^"]+)"', page))

    assert keys
    assert keys <= set(i18n.texts())


def test_page_title_is_the_architecture_name():

    page = HtmlRenderer().render(architecture(), [])

    assert "<title>loja - MFAD</title>" in page


def test_detection_text_is_kept_as_a_reference_for_the_page():
    """A regra grava a frase em português e a referência, que a página traduz."""

    from mfad.adapters.driven import i18n
    from mfad.adapters.driven.antipatterns.rules.global_state_communication import GlobalStateCommunication

    [found] = GlobalStateCommunication().check(architecture())

    assert found.message.startswith("3 micro frontends compartilham 1 fatia")
    assert i18n.t(found.metadata["text"]["message"], "en").startswith("3 micro frontends share 1 slice")


def test_header_numbers_are_tabs_to_the_lists_they_count():
    """Cada número leva à tabela que ele soma, com uma linha por item contado."""

    page = HtmlRenderer().render(architecture(), [])

    tabs = re.findall(r'<button class="metric[^"]*" role="tab" data-page="([^"]+)"', page)

    assert tabs[0] == "home"

    for name in tabs[1:]:

        number = re.search(rf'data-page="{name}" aria-selected="false"><strong>(\d+)</strong>', page)

        section = page.split(f'<div class="page hidden" data-page="{name}"', 1)[1].split('<div class="page', 1)[0]

        # A aba de chamadas tem duas tabelas, endpoints e chamadas: conta
        # a última. Sem item, não há tabela.
        bodies = section.split("<tbody>")[1:]

        rows = bodies[-1].count('<tr class="item"') if bodies else 0

        assert rows == int(number.group(1)), name


def test_file_paths_live_in_the_row_detail_not_in_the_row():
    """A linha cabe na tela; caminho de arquivo é detalhe, que a linha abre."""

    page = HtmlRenderer().render(architecture(), [])

    rows = re.findall(r'<tr class="item".*?</tr>', page)
    details = re.findall(r'<tr class="detail hidden">.*?</tr>', page)

    assert rows and len(rows) == len(details)

    assert not any(".js" in row for row in rows)
    assert any("catalog/Product.js" in detail and ">:9<" in detail for detail in details)

    # E todo detalhe leva a algum lugar do mapa.
    assert all('class="link-button go"' in detail for detail in details)


def test_screen_rows_show_the_fragments_mounted_on_them():

    page = HtmlRenderer().render(architecture(), [])

    section = page.split('<div class="page hidden" data-page="screens"', 1)[1].split('<div class="page', 1)[0]

    [product] = [row for row in re.findall(r'<tr class="item".*?</tr>', section) if ">Product<" in row]

    assert "MiniCart" in product and "cart" in product


def test_fragment_rows_show_who_mounts_them_and_on_which_screens():
    """Fragmentos e composições numa tabela só, aberta pela aba de composições."""

    page = HtmlRenderer().render(architecture(), [])

    assert 'data-page="compositions"' not in page.split('<div class="pages">', 1)[1]
    # Uma aba só, a de composições: duas caixas da mesma tabela
    # ficavam selecionadas juntas.
    assert len(re.findall(r'role="tab" data-page="fragments"', page)) == 1
    assert 'data-t="metric.compositions"' in page and 'data-t="metric.fragments"' not in page

    section = page.split('<div class="page hidden" data-page="fragments"', 1)[1].split('<div class="page', 1)[0]

    [mini_cart] = re.findall(r'<tr class="item".*?</tr>', section)

    cells = re.findall(r"<td[^>]*>(.*?)</td>", mini_cart)

    # chevron, fragmento, provedor, composições, telas
    assert "MiniCart" in cells[1] and cells[3] == "1" and "Product" in cells[4]

    # Quem monta é lista que cresce com o reúso: fica no detalhe.
    detail = section.split(mini_cart, 1)[1].split("</tr>", 1)[0]

    assert ">catalog<" in detail

    # Quem monta é o título do grupo do "composto em", não um campo à parte.
    assert 'data-t="col.defined_at"' in detail and 'data-t="col.composed_at"' in detail
    assert 'data-t="col.mounted_by"' not in detail


def test_external_call_detail_says_where_it_is_called_from():
    """Além do micro frontend: a tela ou o fragmento, e o arquivo."""

    from mfad.domain import ApiCall

    system = architecture()

    system.api_calls = [
        ApiCall(microfrontend="cart", method="GET", path="/cart", match="exact", client="fetch",
                at=at("cart/MiniCart.js", 7), fragments=["MiniCart"]),
        ApiCall(microfrontend="catalog", method="GET", path="/cart", match="exact", client="fetch",
                at=at("catalog/Product.js", 30), screens=["Product"]),
    ]

    page = HtmlRenderer().render(system, [])

    section = page.split('<div class="page hidden" data-page="api_calls"', 1)[1]

    details = re.sub(r"<[^>]+>", "", " ".join(re.findall(r'<tr class="detail hidden">.*?</tr>', section)))

    assert "fragmento MiniCart" in details and "cart/MiniCart.js:7" in details
    assert "tela Product" in details and "catalog/Product.js:30" in details

    # O cliente também, e uma tabela só: a de cada chamada repetia o endpoint.
    assert "fetch" in details
    assert section.split('<div class="page', 1)[0].count('<table') == 1


def test_locations_are_grouped_by_micro_frontend_without_its_directory():
    """O micro frontend aparece uma vez por grupo; o caminho, sem o diretório dele."""

    system = architecture()

    for item in system.microfrontends:
        item.directory = item.id

    system.state_accesses += [
        StateAccess(microfrontend="cart", library="localStorage", path="token", at=at("cart/b.js", 4), access="write"),
    ]

    from mfad.adapters.driven.antipatterns.rules.global_state_communication import GlobalStateCommunication

    page = HtmlRenderer().render(system, GlobalStateCommunication().check(system))

    section = page.split('<div class="page hidden" data-page="detections"', 1)[1].split('<div class="page', 1)[0]

    token = next(row for row in re.findall(r'<tr class="detail hidden">.*?</tr>', section) if "a.js" in row and "b.js" in row)

    owners = re.findall(r'<div class="location-owner"><strong>([^<]+)</strong>', token)

    assert sorted(owners) == ["account", "cart", "catalog"]
    assert '<code title="cart/b.js">b.js</code>' in token and ">:4<" in token
    assert ">cart/b.js" not in token


def test_locations_in_the_same_file_are_one_line():
    """O arquivo que importa e instancia o fragmento aparece uma vez, com as duas linhas."""

    page = HtmlRenderer().render(architecture(), [])

    section = page.split('<div class="page hidden" data-page="fragments"', 1)[1].split('<div class="page', 1)[0]

    [item] = re.findall(r"<li><code[^>]*>catalog/Product.js</code>.*?</li>", section)

    assert ">:1<" in item and ">:9<" in item


def test_detections_are_rows_with_one_field_per_fact():
    """A frase cheia de números vira campos; a dimensão não aparece."""

    from mfad.adapters.driven.antipatterns.rules.global_state_communication import GlobalStateCommunication

    system = architecture()

    page = HtmlRenderer().render(system, GlobalStateCommunication().check(system))

    section = page.split('<div class="page hidden" data-page="detections"', 1)[1].split('<div class="page', 1)[0]

    [row] = re.findall(r'<tr class="item".*?</tr>', section)
    [detail] = re.findall(r'<tr class="detail hidden">.*?</tr>', section)

    assert "global-state-communication" in row
    assert 'data-t="fact.slices"' in detail

    # Qual estado é acessado, por quem e onde: a fatia, não só a contagem.
    assert 'data-t="fact.slice_list"' in detail and "<strong>token</strong>" in detail
    assert 'data-t="col.writers"' in detail

    # Cada fatia fecha: a detecção não cresce com o número de acessos.
    assert '<details class="slice">' in detail and 'data-t="slice.summary"' in detail
    assert 'class="dimension"' not in section
    assert 'data-focus="0"' in detail


def test_route_detections_of_one_anti_pattern_are_one_row_with_a_block_per_route():
    """Uma linha para o hammering, com um bloco que abre por rota."""

    from mfad.adapters.driven.antipatterns.rules.hammering_apis import HammeringApis
    from mfad.domain import ApiCall

    system = architecture()

    system.api_calls = [
        ApiCall(microfrontend=owner, method="GET", path=path, match="exact", client="fetch",
                at=at(f"{owner}/api.js", line))
        for line, (owner, path) in enumerate(
            [("cart", "/cart"), ("catalog", "/cart"), ("cart", "/user"), ("catalog", "/user")], 1
        )
    ]

    found = HammeringApis().check(system)

    assert len(found) == 2

    page = HtmlRenderer().render(system, found)

    section = page.split('<div class="page hidden" data-page="detections"', 1)[1].split('<div class="page', 1)[0]

    [row] = re.findall(r'<tr class="item".*?</tr>', section)
    [detail] = re.findall(r'<tr class="detail hidden">.*?</tr>', section)

    assert "hammering-apis" in row
    assert 'data-t="fact.routes"' in detail and 'data-t="fact.route_list"' in detail
    assert detail.count('<details class="slice">') == 2
    assert "<strong>/cart</strong>" in detail and "<strong>/user</strong>" in detail
    assert 'data-t="endpoint.summary"' in detail

    # Quem martela cada rota está na linha fechada dela.
    assert re.search(r'<strong>/cart</strong>.*?<span class="slice-callers">cart, catalog</span>.*?</summary>', detail)

    # O foco mostra as rotas todas no grafo.
    assert 'data-focus="0,1"' in detail


def test_same_label_in_one_file_is_shown_once_with_its_lines():
    """Três chamadas iguais no mesmo arquivo: a etiqueta uma vez, as três linhas juntas."""

    from mfad.adapters.driven.visualization import tables

    rendered = tables.grouped(
        [
            ("plan", "plan/a.ts", 57, "GET tela X"),
            ("plan", "plan/a.ts", 36, "GET tela X"),
            ("plan", "plan/a.ts", 90, "POST tela Y"),
        ],
        {"plan": "plan"},
    )

    assert rendered.count("GET tela X") == 1
    assert ":36, :57</span> GET tela X" in rendered
    assert ":90</span> POST tela Y" in rendered


def test_detection_without_locations_has_no_code_field():
    """Nano e mega não apontam linha: o campo de código não aparece vazio."""

    from mfad.domain import AntiPatternDetection

    found = AntiPatternDetection(
        anti_pattern="mega-frontend", dimension="", explanation="", message="grande",
        subjects=["cart"], locations=[], metadata={},
    )

    page = HtmlRenderer().render(architecture(), [found])

    section = page.split('<div class="page hidden" data-page="detections"', 1)[1].split('<div class="page', 1)[0]

    [detail] = re.findall(r'<tr class="detail hidden">.*?</tr>', section)

    assert 'data-t="detection.code"' not in detail


def test_micro_frontend_detail_lists_its_screens_and_fragments():
    """A linha conta telas e fragmentos; o detalhe diz quais são."""

    page = HtmlRenderer().render(architecture(), [])

    section = page.split('<div class="page hidden" data-page="microfrontends"', 1)[1].split('<div class="page', 1)[0]

    [cart] = [row for row in re.findall(r'<tr class="item".*?</tr>', section) if "<strong>cart</strong>" in row]

    detail = section.split(cart, 1)[1].split("</tr>", 1)[0]

    assert 'data-t="list.screens"' in detail and ">telas 1<" in detail and "<li>Cart <code>/cart</code></li>" in detail
    assert 'data-t="list.fragments"' in detail and ">fragmentos 1<" in detail and "<li>MiniCart</li>" in detail


def test_details_are_a_closed_sidebar_with_a_close_button():
    """Os detalhes só aparecem ao clicar: a barra lateral começa fechada."""

    page = HtmlRenderer().render(architecture(), [])

    [drawer] = re.findall(r'<aside class="[^"]*drawer[^"]*"[^>]*>', page)

    assert 'aria-hidden="true"' in drawer and "open" not in drawer
    assert 'id="side-close"' in page and 'data-t="side.close"' in page

    # O voltar só aparece depois de seguir um link da barra.
    assert re.search(r'<button class="drawer-back hidden" id="side-back"', page)


def test_table_rows_carry_keys_for_the_sidebar_links():
    """A barra lateral leva à linha pela chave: o micro frontend, a tela, o par."""

    import html

    page = HtmlRenderer().render(architecture(), [])

    def keys(name):
        section = page.split(f'<div class="page hidden" data-page="{name}"', 1)[1].split('<div class="page', 1)[0]
        return [html.unescape(key).split(" ") for key in re.findall(r'<tr class="item" data-key="([^"]+)"', section)]

    assert ["cart"] in keys("microfrontends")
    assert ["cart#Cart", "cart"] in keys("screens")
    assert any("cart#MiniCart" in key and "catalog>cart" in key for key in keys("fragments"))


def test_each_anti_pattern_is_a_tag_with_its_own_color():
    """Na tabela de detecções, o nome é uma etiqueta colorida, uma cor por anti-padrão."""

    from mfad.adapters.driven.antipatterns.rules.global_state_communication import GlobalStateCommunication
    from mfad.adapters.driven.visualization import tables

    system = architecture()

    page = HtmlRenderer().render(system, GlobalStateCommunication().check(system))

    assert '<span class="ap-tag ap-violet">global-state-communication</span>' in page

    # Cores distintas entre os anti-padrões conhecidos, e uma para qualquer outro.
    assert len(set(tables.COLORS.values())) == len(tables.COLORS)
    assert tables.color_of("um-novo") in tables.PALETTE


def test_endpoint_count_is_method_and_path():
    """GET e POST no mesmo caminho são dois endpoints; duas chamadas iguais, um."""

    from mfad.domain import ApiCall

    system = architecture()

    system.api_calls = [
        ApiCall(microfrontend="cart", method=method, path="/cart", match="exact", client="fetch", at=at("cart/api.js", line))
        for line, method in enumerate(["GET", "POST", "GET"], 1)
    ]

    page = HtmlRenderer().render(system, [])

    [metric] = re.findall(r'data-page="api_calls"[^>]*><strong>(\d+)</strong>', page)

    assert metric == "2"


def test_each_detection_links_to_its_definition_in_the_catalog(tmp_path):
    """
    Quem avalia a ocorrência sem conhecer o anti-padrão consulta a
    definição: a detecção leva a referência do catálogo, e a página a
    mostra como link no detalhe da linha.
    """

    from mfad.adapters.driven.antipatterns.rules.global_state_communication import GlobalStateCommunication
    from mfad.application.use_cases.antipatterns.detect import DetectUseCase
    from mfad.adapters.driven.storage.json_repository import JsonArtifactRepository

    rule = GlobalStateCommunication()

    result = DetectUseCase(
        source=tmp_path,
        destination=tmp_path,
        rules=[rule],
        repository=JsonArtifactRepository(),
        architecture=architecture(),
    ).execute()

    [found] = result.detections

    assert found.reference == rule.anti_pattern.reference
    assert found.reference.startswith("https://mfe-anti-patterns.online/")

    page = HtmlRenderer().render(architecture(), result.detections)

    assert f'href="{found.reference}"' in page
