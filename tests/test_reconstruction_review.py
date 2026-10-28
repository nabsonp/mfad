"""
Fixes from the reconstruction review (agent-judge, October 2026).

One test per defect, each with a minimal repository written from the
technology's documentation. The list of defects and fixes is in
`estudo/avaliacao/correcoes-reconstrucao.md`.
"""

from conftest import angular_unit, by_id, mfe, package, react_lifecycles, root_config


ROOT = root_config({"@org/catalog": "/catalog", "@org/checkout": "/checkout"})


# ----------------------------------------------------------------------
# 1. The URL of an HTTP request is not navigation
# ----------------------------------------------------------------------


def test_http_request_to_a_path_that_is_another_route_is_not_navigation(system):
    """
    `axios.get(url)` fetches a resource (https://axios-http.com/docs/api_intro),
    and the function that forwards the URL to a client is a client too: even
    if the path matches another application's route, nobody goes there.
    """

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                import axios from "axios";
                import { navigateToUrl } from "single-spa";
                import { request } from "./api";
                export default function Root() {
                  axios.get("/checkout/summary");
                  request("/checkout/items");
                  navigateToUrl("/checkout");
                  return null;
                }
            """),
            "catalog/src/api.js": """
                import axios from "axios";
                export function request(url) {
                  return axios.get(url);
                }
            """,
            **mfe("checkout", "@org/checkout", "export default () => null;"),
        },
        prefix="@org/",
    )

    assert [item.resolved_url for item in architecture.navigations] == ["/checkout"]
    assert sorted(call.path for call in architecture.api_calls) == ["/checkout/items", "/checkout/summary"]


# ----------------------------------------------------------------------
# 2. The server that serves the bundle does not navigate
# ----------------------------------------------------------------------


def test_server_module_routes_are_not_navigation(system):
    """
    Express declares routes with `app.get(path, handler)`
    (https://expressjs.com/en/guide/routing.html), in a module that runs on
    Node: it imports `path`, which webpack 5 and Vite do not bring to the browser.
    """

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                import { navigateToUrl } from "single-spa";
                export default function Root() {
                  navigateToUrl("/checkout");
                  return null;
                }
            """),
            "catalog/server.js": """
                import express from "express";
                import path from "path";
                const app = express();
                app.get("/checkout", (req, res) => res.sendFile(path.join(__dirname, "index.html")));
                app.listen(8080);
            """,
            **mfe("checkout", "@org/checkout", "export default () => null;"),
        },
        prefix="@org/",
    )

    assert [(item.at.file, item.resolved_url) for item in architecture.navigations] == [
        ("catalog/src/root.component.js", "/checkout"),
    ]


# ----------------------------------------------------------------------
# 3. Comparing with the current URL is not navigating
# ----------------------------------------------------------------------


def test_route_matchers_are_not_navigation(system):
    """
    `useMatch(pattern)` returns whether the current URL matches the pattern
    (https://reactrouter.com/en/main/hooks/use-match), and `matchPath` does the
    same outside a component: neither of them takes the user to the route.
    """

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                import { useMatch, matchPath, useNavigate } from "react-router-dom";
                export default function Root() {
                  const onCheckout = useMatch("/checkout/:step");
                  const matched = matchPath("/checkout", window.location.pathname);
                  const navigate = useNavigate();
                  navigate("/checkout");
                  return null;
                }
            """),
            **mfe("checkout", "@org/checkout", "export default () => null;"),
        },
        prefix="@org/",
    )

    assert [item.at.code for item in architecture.navigations] == ['navigate("/checkout");']


# ----------------------------------------------------------------------
# 4. A fragment is a component, not just any export
# ----------------------------------------------------------------------


def test_exported_data_is_not_a_fragment(system):
    """
    A React component is a function or a class (https://react.dev/reference/react/Component).
    The texts object and the TypeScript type come out through the same
    `export`, but nobody mounts them. Follows `export ... from` to the declaration.
    """

    architecture = system(
        {
            **ROOT,
            "catalog/package.json": package("@org/catalog"),
            "catalog/src/org-catalog.tsx": react_lifecycles() + """
                export { locale, Card, api } from "./services";
                export type CardProps = { title: string };
                export const VERSION = "1.0";
            """,
            "catalog/src/services/index.ts": """
                export { default as locale } from "./locale";
                export { Card } from "./card";
                export * as api from "./api";
            """,
            "catalog/src/services/api.ts": "export const list = () => fetch('/items');",
            "catalog/src/services/locale.ts": """
                const locale = { title: "Catálogo", components: { card: "Cartão" } };
                export default locale;
            """,
            "catalog/src/services/card.tsx": "export const Card = ({ title }) => <div>{title}</div>;",
            "catalog/src/root.component.js": "export default () => null;",
            **mfe("checkout", "@org/checkout", "export default () => null;"),
        },
        prefix="@org/",
    )

    assert [fragment.name for fragment in by_id(architecture, "catalog").fragments] == ["Card"]


# ----------------------------------------------------------------------
# 5. A route that only redirects is not a screen
# ----------------------------------------------------------------------


def test_redirect_route_is_not_a_screen(system):
    """
    `<Redirect>` (React Router v5, https://v5.reactrouter.com/web/api/Redirect)
    and `<Navigate>` (v6, https://reactrouter.com/6.30.0/components/navigate)
    lead to another route: the route that renders them shows no screen.
    """

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                import { Switch, Route, Redirect, Routes, Navigate } from "react-router-dom";
                import List from "./List";
                export default function Root() {
                  return (
                    <>
                      <Switch>
                        <Route path="/catalog/list"><List /></Route>
                        <Route path="*"><Redirect to="/catalog/list" /></Route>
                      </Switch>
                      <Routes>
                        <Route path="/catalog/old" element={<Navigate to="/catalog/list" />} />
                      </Routes>
                    </>
                  );
                }
            """),
            "catalog/src/List.js": "export default () => null;",
            **mfe("checkout", "@org/checkout", "export default () => null;"),
        },
        prefix="@org/",
    )

    assert [screen.component for screen in by_id(architecture, "catalog").screens] == ["List"]


# ----------------------------------------------------------------------
# 6. Lazily loaded routes respond below whoever loads them
# ----------------------------------------------------------------------


def test_lazy_loaded_angular_routes_keep_the_parent_path(system):
    """
    `{ path: "admin", loadChildren: () => import("./admin.routes") }` puts the
    loaded routes under `/admin` (https://angular.dev/guide/ngmodules/lazy-loading),
    whether it is the routes file or the `NgModule` that registers them with `forChild`.
    """

    architecture = system(
        angular_unit(
            "reports",
            {
                "app.routes.ts": """
                    import { Routes } from "@angular/router";
                    export const routes: Routes = [
                      { path: "inscriptions", loadChildren: () => import("./inscriptions/inscriptions.routes").then((m) => m.ROUTES) },
                      { path: "legacy", loadChildren: () => import("./legacy/legacy.module").then((m) => m.LegacyModule) },
                    ];
                """,
                "inscriptions/inscriptions.routes.ts": """
                    import { Routes } from "@angular/router";
                    export const ROUTES: Routes = [
                      { path: "applicants", loadComponent: () => import("./applicants").then((m) => m.Applicants) },
                    ];
                """,
                "inscriptions/applicants.ts": "export class Applicants {}",
                "legacy/legacy.module.ts": """
                    import { NgModule } from "@angular/core";
                    import { LegacyRoutingModule } from "./legacy-routing.module";
                    @NgModule({ imports: [LegacyRoutingModule] })
                    export class LegacyModule {}
                """,
                "legacy/legacy-routing.module.ts": """
                    import { NgModule } from "@angular/core";
                    import { RouterModule, Routes } from "@angular/router";
                    import { HistoryComponent } from "./history.component";
                    const routes: Routes = [{ path: "history", component: HistoryComponent }];
                    @NgModule({ imports: [RouterModule.forChild(routes)] })
                    export class LegacyRoutingModule {}
                """,
                "legacy/history.component.ts": "export class HistoryComponent {}",
            },
        )
    )

    assert sorted((screen.component, screen.route) for screen in by_id(architecture, "reports").screens) == [
        ("Applicants", "/inscriptions/applicants"),
        ("HistoryComponent", "/legacy/history"),
    ]


# ----------------------------------------------------------------------
# 7. The location of the screen and the fragment is the component definition
# ----------------------------------------------------------------------


def test_screen_and_fragment_point_to_the_component_definition(system):
    """
    The route (in the root component) and the `export` (in the entrypoint) are
    in another file; the location is the component's: the file and line of the
    declaration, or of the `export default` when the default import gives it
    another name.
    """

    architecture = system(
        {
            **ROOT,
            "catalog/package.json": package("@org/catalog"),
            "catalog/src/org-catalog.js": react_lifecycles() + """
                export { Card } from "./Card";
            """,
            "catalog/src/root.component.js": """
                import { Routes, Route } from "react-router-dom";
                import Home from "./Home";
                import { Search } from "./views";
                export default function Root() {
                  return (
                    <Routes>
                      <Route path="/catalog" element={<Home />} />
                      <Route path="/catalog/search" element={<Search />} />
                    </Routes>
                  );
                }
            """,
            "catalog/src/views/index.js": 'export { Search } from "./search";',
            "catalog/src/views/search.js": """
                import React from "react";
                export function Search() {
                  return null;
                }
            """,
            "catalog/src/Home.js": """
                import React from "react";

                export default function HomePage() {
                  return null;
                }
            """,
            "catalog/src/Card.js": """
                // Cartão do produto.

                export const Card = () => null;
            """,
            **mfe("checkout", "@org/checkout", "export default () => null;"),
        },
        prefix="@org/",
    )

    catalog = by_id(architecture, "catalog")

    assert [(screen.file, screen.line) for screen in catalog.screens] == [
        ("catalog/src/Home.js", 3),
        ("catalog/src/views/search.js", 2),
    ]
    assert [(fragment.file, fragment.line) for fragment in catalog.fragments] == [("catalog/src/Card.js", 3)]


# ----------------------------------------------------------------------
# 9. The micro frontend is identified by its directory
# ----------------------------------------------------------------------


def test_microfrontend_is_named_after_its_directory(system):
    """
    The name in `registerApplication` (https://single-spa.js.org/docs/api#registerapplication)
    is what the orchestrator uses; readers look the micro frontend up by
    repository. The registered name is kept, and every reference follows.
    """

    architecture = system(
        {
            **root_config({"@org/tipo-inscripcion": "/catalog", "@org/checkout": "/checkout"}),
            **mfe("admin_mf", "@org/tipo-inscripcion", """
                import { navigateToUrl } from "single-spa";
                export default function Root() {
                  navigateToUrl("/checkout");
                  return null;
                }
            """),
            **mfe("checkout", "@org/checkout", "export default () => null;"),
        },
        prefix="@org/",
    )

    admin = by_id(architecture, "admin_mf")

    assert admin.metadata["registered_name"] == "@org/tipo-inscripcion"
    assert [(item.source, item.target) for item in architecture.navigations] == [("admin_mf", "checkout")]


# ----------------------------------------------------------------------
# 10. The root that only mounts providers is not the screen
# ----------------------------------------------------------------------


def test_root_that_only_wraps_providers_is_not_the_screen(system):
    """
    Without an internal router, the micro frontend shows one screen at the
    `activeWhen` prefix. The root component that only mounts Redux's
    `<Provider>` (https://react-redux.js.org/api/provider) around `App` is not
    it: the screen is `App`, the first one with content of its own.
    """

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", """
                import { Provider } from "react-redux";
                import store from "./store";
                import App from "./App";
                export default function Root() {
                  return (
                    <Provider store={store}>
                      <App />
                    </Provider>
                  );
                }
            """),
            "catalog/src/store.js": "export default {};",
            "catalog/src/App.js": """
                const App = () => <div className="catalog">Catálogo</div>;
                export default App;
            """,
            **mfe("checkout", "@org/checkout", "export default () => null;"),
        },
        prefix="@org/",
    )

    assert [(screen.component, screen.file, screen.route) for screen in by_id(architecture, "catalog").screens] == [
        ("App", "catalog/src/App.js", "/catalog"),
    ]


# ----------------------------------------------------------------------
# 11. A generator template is not a micro frontend
# ----------------------------------------------------------------------


def test_generator_template_is_not_a_microfrontend(system):
    """
    A `package.json` with template markup (`"<%= name %>"`, with no quotes
    around the value) is not JSON, and npm does not install the package
    (https://docs.npmjs.com/cli/configuring-npm/package-json): the lifecycles
    in the template do not make it a unit.
    """

    architecture = system(
        {
            **ROOT,
            **mfe("catalog", "@org/catalog", "export default () => null;"),
            **mfe("checkout", "@org/checkout", "export default () => null;"),
            "generator/templates/package.json": '{\\n  "name": "<%= name %>",\\n  <% if (npm) { %> "private": true, <% } %>\\n}',
            "generator/templates/src/main.js": react_lifecycles(),
            "generator/templates/src/root.component.js": "export default () => null;",
        },
    )

    assert sorted(item.id for item in architecture.microfrontends) == ["catalog", "checkout", "root-config"]
