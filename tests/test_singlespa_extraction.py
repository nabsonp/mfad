"""
Extração single-spa: fragmentos, eventos, estado, navegação e registro.

Cada caso é uma forma comum de escrever a mesma coisa que a extração
já reconhecia em outra forma.
"""

from conftest import by_id, mfe, package, react_lifecycles, root_config


ROOT = root_config({"@org/catalog": "/catalog", "@org/checkout": "/checkout"})


def channels(architecture, mechanism="CustomEvent"):
    return sorted(
        (item.source, item.target, item.channel)
        for item in architecture.communications
        if item.mechanism == mechanism and item.directed
    )


# ----------------------------------------------------------------------
# Eventos
# ----------------------------------------------------------------------


def test_event_created_before_being_dispatched(system):
    """`const e = new CustomEvent("x"); window.dispatchEvent(e)`."""

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                export function addToCart(item) {
                  const event = new CustomEvent("cart:add", { detail: item });
                  window.dispatchEvent(event);
                }
                export default () => <button onClick={() => addToCart(1)} />;
            """),
            **mfe("checkout", "@org/checkout", """
                window.addEventListener("cart:add", (e) => console.log(e.detail));
                export default () => null;
            """),
        },
        prefix="@org/",
    )

    assert channels(architecture) == [("@org/catalog", "@org/checkout", "cart:add")]


def test_rxjs_from_event_on_window_listens(system):
    """https://rxjs.dev/api/index/function/fromEvent"""

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                window.dispatchEvent(new CustomEvent("lang", { detail: "pt" }));
                export default () => null;
            """),
            **mfe("checkout", "@org/checkout", """
                import { fromEvent } from "rxjs";
                fromEvent(window, "lang").subscribe(() => {});
                fromEvent(button, "click").subscribe(() => {});
                export default () => null;
            """),
        },
        prefix="@org/",
    )

    assert channels(architecture) == [("@org/catalog", "@org/checkout", "lang")]


def test_event_name_from_a_shared_constant(system):

    architecture = system(
        {
            **ROOT,
            "events/package.json": package("@org/events", **{"react": "^18"}),
            "events/src/index.js": 'export const CART_UPDATED = "cart:updated";',
            **mfe("catalog", "@org/catalog", """
                import { CART_UPDATED } from "@org/events";
                window.dispatchEvent(new CustomEvent(CART_UPDATED));
                export default () => null;
            """),
            **mfe("checkout", "@org/checkout", """
                window.addEventListener("cart:updated", () => {});
                export default () => null;
            """),
        },
        prefix="@org/",
    )

    assert channels(architecture) == [("@org/catalog", "@org/checkout", "cart:updated")]


# ----------------------------------------------------------------------
# Estado
# ----------------------------------------------------------------------


def test_storage_key_in_a_constant(system):

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                const CART_KEY = "cart";
                localStorage.setItem(CART_KEY, "[]");
                export default () => null;
            """),
            **mfe("checkout", "@org/checkout", """
                import { CART_KEY } from "./keys";
                localStorage.getItem(CART_KEY);
                export default () => null;
            """),
            "checkout/src/keys.js": 'export const CART_KEY = "cart";',
        },
        prefix="@org/",
    )

    assert sorted((item.microfrontend, item.path, item.access) for item in architecture.state_accesses) == [
        ("@org/catalog", "cart", "write"),
        ("@org/checkout", "cart", "read"),
    ]


def test_constant_with_two_values_is_not_resolved(system):
    """O mesmo nome com valores diferentes: não se sabe qual é."""

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                const KEY = "cart";
                localStorage.getItem(KEY);
                export default () => null;
            """),
            **mfe("checkout", "@org/checkout", """
                const KEY = "user";
                localStorage.getItem(KEY);
                export default () => null;
            """),
        },
        prefix="@org/",
    )

    assert architecture.state_accesses == []


# ----------------------------------------------------------------------
# Navegação
# ----------------------------------------------------------------------


def test_route_declarations_and_fetch_are_not_navigations(system):

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                import { Route, Link } from "react-router-dom";
                export default function Root() {
                  fetch("/checkout/summary");
                  return (
                    <>
                      <Route path="/checkout" element={<Page />} />
                      <Link to="/checkout">Finalizar</Link>
                      <BackButton path="/checkout" />
                    </>
                  );
                }
            """),
            **mfe("checkout", "@org/checkout", "export default () => null;"),
        },
        prefix="@org/",
    )

    # O `path` da `<Route>` declara; o do componente do projeto navega.
    assert sorted(item.at.code for item in architecture.navigations) == [
        'path="/checkout"',
        'to="/checkout"',
    ]
    assert {(item.source, item.target) for item in architecture.navigations} == {
        ("@org/catalog", "@org/checkout")
    }


# ----------------------------------------------------------------------
# Inventário
# ----------------------------------------------------------------------


def test_locals_inside_exported_functions_are_not_fragments(system):
    """O `let el` de `export function domElementGetter()` não é exportado."""

    architecture = system(
        {
            **ROOT,
            "catalog/package.json": package("@org/catalog"),
            "catalog/src/org-catalog.js": react_lifecycles() + """
                export function domElementGetter() {
                  let el = document.getElementById("catalog");
                  return el;
                }
                export const CatalogCard = () => null;
            """,
            "catalog/src/root.component.js": "export default () => null;",
        },
        prefix="@org/",
    )

    assert [fragment.name for fragment in by_id(architecture, "@org/catalog").fragments] == ["CatalogCard"]


def test_shorthand_custom_props_are_channels(system):

    architecture = system(
        {
            "root-config/package.json": package("@org/root-config"),
            "root-config/src/org-root-config.js": """
                import { registerApplication } from "single-spa";
                import { store } from "./store";
                registerApplication({
                  name: "@org/catalog",
                  app: () => System.import("@org/catalog"),
                  activeWhen: ["/catalog"],
                  customProps: { store, theme: "dark" },
                });
            """,
            **mfe("catalog", "@org/catalog", "export default () => null;"),
        },
        prefix="@org/",
    )

    assert by_id(architecture, "@org/catalog").metadata["custom_props"] == {"store": "", "theme": "dark"}


def test_registration_with_a_runtime_name_is_not_an_application(system):
    """`registerApplication(appName, ...)` num laço não cria a aplicação `appName`."""

    architecture = system(
        {
            "framework/package.json": package("@org/framework"),
            "framework/src/pages.js": """
                import { registerApplication } from "single-spa";
                export function registerPages(pages) {
                  for (const { appName, load, route } of pages) {
                    registerApplication(appName, load, route);
                  }
                }
            """,
        },
    )

    assert [item.id for item in architecture.microfrontends] == []


def test_redux_store_created_inside_the_unit_is_local_state(system):
    """Cada unidade com o próprio `createStore`: mesma fatia, stores diferentes."""

    def unit(directory, name):
        return mfe(directory, name, """
            import { createStore } from "redux";
            import { useSelector } from "react-redux";
            export const store = createStore((state = {}) => state);
            export default function Root() {
              const lookup = useSelector((state) => state.lookup);
              return null;
            }
        """)

    architecture = system(
        {**ROOT, **unit("catalog", "@org/catalog"), **unit("checkout", "@org/checkout")},
        prefix="@org/",
    )

    assert architecture.state_accesses == []


def test_redux_store_injected_by_the_shell_is_shared(system):

    def unit(directory, name):
        return mfe(directory, name, """
            import { useSelector } from "react-redux";
            export default function Root() {
              const cart = useSelector((state) => state.cart);
              return null;
            }
        """)

    architecture = system(
        {**ROOT, **unit("catalog", "@org/catalog"), **unit("checkout", "@org/checkout")},
        prefix="@org/",
    )

    assert sorted((item.microfrontend, item.path) for item in architecture.state_accesses) == [
        ("@org/catalog", "cart"),
        ("@org/checkout", "cart"),
    ]


def test_text_method_arguments_are_not_navigations(system):
    """`url.endsWith("/catalog")` compara texto; não leva a lugar nenhum."""

    architecture = system(
        {
            **root_config({"@org/catalog": "/catalog", "@org/checkout": "/checkout"}),
            **mfe("checkout", "@org/checkout", """
                export default function Root() {
                  const here = window.location.pathname.startsWith("/catalog");
                  const parts = "/catalog/x".split("/catalog");
                  return null;
                }
            """),
            **mfe("catalog", "@org/catalog", "export default () => null;"),
        },
        prefix="@org/",
    )

    assert architecture.navigations == []


def test_typescript_as_const_object_resolves(system):
    """`export const ROUTES = { AUTH: "/auth" } as const;`"""

    architecture = system(
        {
            **root_config({"@org/auth": "/auth", "@org/drawer": "/drawer"}),
            **mfe("auth", "@org/auth", "export default () => null;"),
            **mfe("drawer", "@org/drawer", """
                import { navigateToUrl } from "single-spa";
                import { ROUTES } from "./constants";
                export default function Root() {
                  return <button onClick={() => navigateToUrl(ROUTES.AUTH)}>Sair</button>;
                }
            """),
            "drawer/src/constants.ts": """
                export const ROUTES = { AUTH: "/auth", HOME: "/drawer" } as const;
            """,
        },
        prefix="@org/",
    )

    assert [(item.source, item.target, item.resolved_url) for item in architecture.navigations] == [
        ("@org/drawer", "@org/auth", "/auth")
    ]


def test_event_from_a_function_nobody_calls_is_not_a_channel(system):
    """O arquivo é importado, mas não a função que dispara o evento."""

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                import { readAccount } from "./account";
                export default () => <p>{readAccount()}</p>;
            """),
            "catalog/src/account.js": """
                export function readAccount() {
                  return localStorage.getItem("account");
                }
                export function saveAccount(id) {
                  window.dispatchEvent(new CustomEvent("account:changed", { detail: id }));
                }
                function neverCalled() {
                  window.dispatchEvent(new CustomEvent("account:reset"));
                }
                function called() {
                  window.dispatchEvent(new CustomEvent("account:loaded"));
                }
                called();
            """,
            **mfe("checkout", "@org/checkout", """
                window.addEventListener("account:changed", () => {});
                window.addEventListener("account:reset", () => {});
                window.addEventListener("account:loaded", () => {});
                export default () => null;
            """),
        },
        prefix="@org/",
    )

    assert channels(architecture) == [("@org/catalog", "@org/checkout", "account:loaded")]


def test_typed_event_is_still_the_event(system):
    """`new CustomEvent("x") as EventoTipado` em TypeScript."""

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                import { select } from "./account";
                export default () => <button onClick={() => select("1")} />;
            """),
            "catalog/src/account.ts": """
                export function select(id: string): void {
                  const event = new CustomEvent("account:changed", { detail: { id } }) as AccountChanged;
                  window.dispatchEvent(event);
                }
            """,
            **mfe("checkout", "@org/checkout", """
                window.addEventListener("account:changed", () => {});
                export default () => null;
            """),
        },
        prefix="@org/",
    )

    assert channels(architecture) == [("@org/catalog", "@org/checkout", "account:changed")]


def test_navigation_knows_the_screen_it_leaves_from(system):
    """O botão que leva ao checkout está na tela do catálogo."""

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                import { BrowserRouter, Routes, Route } from "react-router-dom";
                import Products from "./Products";
                export default function Root() {
                  return (
                    <BrowserRouter>
                      <Routes><Route path="/catalog" element={<Products />} /></Routes>
                    </BrowserRouter>
                  );
                }
            """),
            "catalog/src/Products.js": """
                import { navigateToUrl } from "single-spa";
                export default function Products() {
                  return <button onClick={() => navigateToUrl("/checkout")}>Comprar</button>;
                }
            """,
            **mfe("checkout", "@org/checkout", "export default () => null;"),
        },
        prefix="@org/",
    )

    [navigation] = architecture.navigations

    assert navigation.on.screens == ["@org/catalog#Products"]
