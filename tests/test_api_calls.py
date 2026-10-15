"""Chamadas a serviço externo e o `hammering-apis` que depende delas."""

from conftest import mfe, root_config

from damfe.adapters.driven.antipatterns.rules.hammering_apis import HammeringApis


ROOT = root_config({"@org/catalog": "/catalog", "@org/checkout": "/checkout"})


def test_url_after_an_environment_base_keeps_its_path(system):
    """`${API_URL}/users` é a forma comum: a base vem de variável de ambiente."""

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                const API_URL = process.env.API_URL;
                export default function Root() {
                  fetch(`${API_URL}/users/${id}`);
                  fetch(`${API_URL}/products`);
                  return null;
                }
            """),
            **mfe("checkout", "@org/checkout", """
                import axios from "axios";
                export default function Root() {
                  axios.get(process.env.API_URL + "/products");
                  return null;
                }
            """),
        },
        prefix="@org/",
    )

    calls = sorted((call.microfrontend, call.path, call.match) for call in architecture.api_calls)

    assert calls == [
        ("catalog", "/products", "exact"),
        # O trecho de runtime vira `{param}`: o recurso continua
        # identificado pelo que vem depois dele.
        ("catalog", "/users/{param}", "pattern"),
        ("checkout", "/products", "exact"),
    ]

    [found] = HammeringApis().check(architecture)

    assert found.metadata["path"] == "/products"
    assert found.metadata["callers"] == ["catalog", "checkout"]


def test_unknown_base_is_never_a_navigation(system):
    """`${CDN}/checkout` pode ser outra origem; não é rota do sistema."""

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                export default function Root() {
                  return <a href={`${CDN_URL}/checkout`}>x</a>;
                }
            """),
            **mfe("checkout", "@org/checkout", "export default () => null;"),
        },
        prefix="@org/",
    )

    assert architecture.navigations == []


def test_storage_key_built_at_runtime_is_not_a_slice(system):
    """`"cart_" + id` não diz qual fatia é; o começo não é a chave."""

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                export default function Root() {
                  localStorage.getItem("cart_" + userId);
                  localStorage.getItem("theme");
                  return null;
                }
            """),
        },
        prefix="@org/",
    )

    assert [access.path for access in architecture.state_accesses] == ["theme"]


def test_path_without_a_literal_segment_is_not_an_endpoint(system):

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                export default function Root() {
                  fetch(`${API_URL}/${resource}`);
                  fetch(`/${resource}`);
                  const target = `http://localhost:${port}${request.url}`;
                  fetch(target);
                  return null;
                }
            """),
        },
        prefix="@org/",
    )

    assert architecture.api_calls == []


def test_runtime_segment_keeps_the_rest_of_the_path(system):
    """`/account/${id}/statement` e `/account/${id}/transfers` são rotas diferentes."""

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                export default function Root() {
                  fetch(`/account/${id}/statement`);
                  fetch(`/account/${id}/statement/`);
                  fetch("/account/" + id + "/transfers?page=" + page);
                  fetch(`/account//${id}//transfers`);
                  return null;
                }
            """),
        },
        prefix="@org/",
    )

    # A barra no fim e a repetida não mudam o recurso.
    assert sorted(call.path for call in architecture.api_calls) == [
        "/account/{param}/statement",
        "/account/{param}/statement",
        "/account/{param}/transfers",
        "/account/{param}/transfers",
    ]
