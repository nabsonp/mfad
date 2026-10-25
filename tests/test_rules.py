"""
Regras de detecção, sobre arquiteturas montadas à mão.

A detecção só lê artefatos, então os casos são escritos direto no
modelo: o teste prova a regra sem depender de extrator nenhum.
"""

from mfad.adapters.driven.antipatterns.rules.cyclic_dependency import CyclicDependency
from mfad.adapters.driven.antipatterns.rules.global_state_communication import (
    GlobalStateCommunication,
)
from mfad.adapters.driven.antipatterns.rules.hub_like_dependency import HubLikeDependency
from mfad.adapters.driven.antipatterns.rules.nano_frontend import NanoFrontend
from mfad.adapters.driven.antipatterns.rules.one_for_all import OneForAll
from mfad.domain import (
    CodeSize,
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


def at(file: str) -> SourceLocation:
    return SourceLocation(file=file, line=1)


A, B, C = "@o/a", "@o/b", "@o/c"


def event(source, target, channel, produced_on, consumed_on) -> Communication:
    return Communication(
        source, target, "custom-event", channel, [at("p.js")], [at("c.js")],
        produced_on=produced_on, consumed_on=consumed_on,
    )


# ----------------------------------------------------------------------
# cyclic-dependency
# ----------------------------------------------------------------------


def _cyclic_architecture() -> MicroFrontendArchitecture:

    return MicroFrontendArchitecture(
        microfrontends=[
            MicroFrontend(id=A, screens=[Screen("Home", A), Screen("Other", A)], fragments=[Fragment("FA", A)]),
            MicroFrontend(id=B, fragments=[Fragment("FB", B)]),
            MicroFrontend(id=C, screens=[Screen("Page", C)]),
        ],
        compositions=[
            # Home (de A) monta FB; FB monta FA: ciclo A → B → A na Home.
            Composition(A, B, "FB", "FB", at("a/home.js"), [RenderLocation("a/home.js", 3, screens=[f"{A}#Home"])]),
            Composition(B, A, "FA", "FA", at("b/fb.js"), [RenderLocation("b/fb.js", 5, fragments=[f"{B}#FB"])]),
        ],
        communications=[
            # Na Home: A publica, FB (de B) consome; FB publica, A consome.
            event(A, B, "x", Placement([f"{A}#Home"]), Placement(fragments=[f"{B}#FB"])),
            event(B, A, "y", Placement(fragments=[f"{B}#FB"]), Placement([f"{A}#Home"])),
            # A ↔ C, mas cada ponta numa tela diferente: não coexistem.
            event(A, C, "z", Placement([f"{A}#Other"]), Placement([f"{C}#Page"])),
            event(C, A, "w", Placement([f"{C}#Page"]), Placement([f"{A}#Other"])),
        ],
        navigations=[
            Navigation(A, C, "", "/c", "exact", at("a/x.js")),
            Navigation(C, A, "", "/a", "exact", at("c/x.js")),
        ],
    )


def test_cycle_inside_one_screen_is_found_per_relation():

    found = CyclicDependency().check(_cyclic_architecture())

    assert sorted((item.metadata["relation"], tuple(item.metadata["chain"])) for item in found) == [
        ("communication", (A, B, A)),
        ("composition", (A, B, A)),
    ]
    assert all(item.metadata["screens"] == [f"{A}#Home"] for item in found)


def test_cycle_across_screens_and_navigation_cycles_are_not_reported():

    found = CyclicDependency().check(_cyclic_architecture())

    assert not any(C in item.subjects for item in found)


def test_undirected_state_edges_never_form_cycles():

    architecture = MicroFrontendArchitecture(
        microfrontends=[MicroFrontend(id=A, screens=[Screen("Home", A)]), MicroFrontend(id=B)],
        communications=[
            Communication(A, B, "global-state", "localStorage:token", [], [], directed=False,
                          produced_on=Placement([f"{A}#Home"]), consumed_on=Placement([f"{A}#Home"])),
            Communication(B, A, "global-state", "localStorage:token", [], [], directed=False,
                          produced_on=Placement([f"{A}#Home"]), consumed_on=Placement([f"{A}#Home"])),
        ],
    )

    assert CyclicDependency().check(architecture) == []


# ----------------------------------------------------------------------
# one-for-all
# ----------------------------------------------------------------------


def _peers(count: int) -> list[MicroFrontend]:
    return [MicroFrontend(id=f"@o/m{index}") for index in range(count)]


def test_one_for_all_counts_directed_edges():

    peers = _peers(6)
    hub = peers[0].id

    architecture = MicroFrontendArchitecture(
        microfrontends=peers,
        navigations=[Navigation(hub, other.id, "", "/x", "exact", at("h.js")) for other in peers[1:]],
    )

    found = OneForAll().check(architecture)

    assert [item.subjects[0] for item in found] == [hub]


def test_one_for_all_ignores_shared_state():
    """Um token lido por todos liga todos a todos, sem centro."""

    peers = _peers(6)

    architecture = MicroFrontendArchitecture(
        microfrontends=peers,
        communications=[
            Communication(a.id, b.id, "global-state", "localStorage:token", [], [], directed=False)
            for a in peers for b in peers if a is not b
        ],
    )

    assert OneForAll().check(architecture) == []


# ----------------------------------------------------------------------
# global-state-communication
# ----------------------------------------------------------------------


def test_same_key_in_different_libraries_is_not_the_same_slice():

    architecture = MicroFrontendArchitecture(
        microfrontends=[MicroFrontend(id=A), MicroFrontend(id=B)],
        state_accesses=[
            StateAccess(A, "localStorage", "user", at("a.js")),
            StateAccess(B, "react-redux", "user", at("b.js")),
        ],
    )

    assert GlobalStateCommunication().check(architecture) == []


def test_storage_key_touched_by_two_units_is_reported():

    architecture = MicroFrontendArchitecture(
        microfrontends=[MicroFrontend(id=A), MicroFrontend(id=B)],
        state_accesses=[
            StateAccess(A, "localStorage", "token", at("a.js"), access="write"),
            StateAccess(B, "localStorage", "token", at("b.js")),
        ],
    )

    [found] = GlobalStateCommunication().check(architecture)

    assert found.metadata["slices"] == {"localStorage:token": [A, B]}


# ----------------------------------------------------------------------
# hub-like-dependency
# ----------------------------------------------------------------------


def _hosting(fragments: list[tuple[str, str]]) -> MicroFrontendArchitecture:
    """Uma tela de A que instancia os fragmentos dados (provedor, nome)."""

    return MicroFrontendArchitecture(
        microfrontends=[MicroFrontend(id=A, screens=[Screen("Home", A)]), MicroFrontend(id=B), MicroFrontend(id=C)],
        compositions=[
            Composition(A, provider, name, name, at("a.js"), [RenderLocation("a.js", line, screens=[f"{A}#Home"])])
            for line, (provider, name) in enumerate(fragments)
        ],
    )


def test_hub_counts_distinct_fragments_not_render_sites():
    """O mesmo card repetido cinco vezes é uma dependência só."""

    repeated = _hosting([(B, "Card")] * 5)

    assert HubLikeDependency().check(repeated) == []

    distinct = _hosting([(B, f"F{index}") for index in range(3)] + [(C, "F0"), (C, "F9")])

    [found] = HubLikeDependency().check(distinct)

    assert "5 fragmentos" in found.message


# ----------------------------------------------------------------------
# nano-frontend
# ----------------------------------------------------------------------


def _sized(name: str, screens: int, lines: int) -> MicroFrontend:
    return MicroFrontend(
        id=name,
        screens=[Screen(f"S{index}", name) for index in range(screens)],
        size=CodeSize(code_lines=lines),
    )


def test_few_screens_with_much_code_is_not_nano():
    """Duas rotas, dezenas de abas: poucas telas, das maiores em código."""

    architecture = MicroFrontendArchitecture(
        microfrontends=[
            _sized("dense", 2, 30_000),
            _sized("tiny", 1, 300),
            _sized("mid1", 8, 5_000),
            _sized("mid2", 9, 6_000),
        ]
    )

    flagged = [item.subjects[0] for item in NanoFrontend().check(architecture)]

    assert flagged == ["tiny"]


def test_global_state_locations_are_listed_once():

    shared = at("shared.js")

    architecture = MicroFrontendArchitecture(
        microfrontends=[MicroFrontend(id=A), MicroFrontend(id=B)],
        state_accesses=[
            StateAccess(A, "react-redux", "cart", shared),
            StateAccess(A, "react-redux", "user", shared),
            StateAccess(B, "react-redux", "cart", at("b.js")),
            StateAccess(B, "react-redux", "user", at("b.js")),
        ],
    )

    [found] = GlobalStateCommunication().check(architecture)

    assert [(item.file, item.line) for item in found.locations] == [("shared.js", 1), ("b.js", 1)]
