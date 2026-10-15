"""
Correções da revisão da reconstrução (agent-judge, outubro de 2026).

Um teste por defeito, cada um com um repositório mínimo escrito a
partir da documentação da tecnologia. A lista dos defeitos e das
correções está em `estudo/avaliacao/correcoes-reconstrucao.md`.
"""

from conftest import angular_unit, by_id, mfe, package, react_lifecycles, root_config


ROOT = root_config({"@org/catalog": "/catalog", "@org/checkout": "/checkout"})


# ----------------------------------------------------------------------
# 1. A URL de uma requisição HTTP não é navegação
# ----------------------------------------------------------------------


def test_http_request_to_a_path_that_is_another_route_is_not_navigation(system):
    """
    `axios.get(url)` busca um recurso (https://axios-http.com/docs/api_intro),
    e a função que repassa a URL a um cliente é cliente também: mesmo que o
    caminho coincida com a rota de outra aplicação, ninguém vai até lá.
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
# 2. O servidor que entrega o pacote não navega
# ----------------------------------------------------------------------


def test_server_module_routes_are_not_navigation(system):
    """
    O Express declara rotas com `app.get(caminho, handler)`
    (https://expressjs.com/en/guide/routing.html), num módulo que roda no
    Node: importa `path`, que o webpack 5 e o Vite não levam ao navegador.
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
# 3. Comparar com a URL atual não é navegar
# ----------------------------------------------------------------------


def test_route_matchers_are_not_navigation(system):
    """
    `useMatch(padrão)` devolve se a URL atual casa com o padrão
    (https://reactrouter.com/en/main/hooks/use-match), e `matchPath` faz o
    mesmo fora de componente: nenhum dos dois leva o usuário à rota.
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
# 4. Fragmento é componente, não qualquer export
# ----------------------------------------------------------------------


def test_exported_data_is_not_a_fragment(system):
    """
    Componente React é função ou classe (https://react.dev/reference/react/Component).
    O objeto de textos e o tipo do TypeScript saem pelo mesmo `export`, mas
    ninguém os monta. Segue o `export ... from` até a declaração.
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
# 5. Rota que só redireciona não é tela
# ----------------------------------------------------------------------


def test_redirect_route_is_not_a_screen(system):
    """
    `<Redirect>` (React Router v5, https://v5.reactrouter.com/web/api/Redirect)
    e `<Navigate>` (v6, https://reactrouter.com/6.30.0/components/navigate)
    levam a outra rota: a rota que os renderiza não mostra tela.
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
# 6. Rotas carregadas sob demanda respondem abaixo de quem as carrega
# ----------------------------------------------------------------------


def test_lazy_loaded_angular_routes_keep_the_parent_path(system):
    """
    `{ path: "admin", loadChildren: () => import("./admin.routes") }` põe as
    rotas carregadas sob `/admin` (https://angular.dev/guide/ngmodules/lazy-loading),
    seja o arquivo das rotas, seja o `NgModule` que as registra com `forChild`.
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
# 7. O local da tela e do fragmento é a definição do componente
# ----------------------------------------------------------------------


def test_screen_and_fragment_point_to_the_component_definition(system):
    """
    A rota (no componente raiz) e o `export` (no entrypoint) estão em outro
    arquivo; o local é o do componente: o arquivo e a linha da declaração,
    ou do `export default` quando o import padrão lhe dá outro nome.
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
# 9. O micro frontend é identificado pelo diretório
# ----------------------------------------------------------------------


def test_microfrontend_is_named_after_its_directory(system):
    """
    O nome do `registerApplication` (https://single-spa.js.org/docs/api#registerapplication)
    é o que o orquestrador usa; quem lê procura o micro frontend pelo
    repositório. O nome registrado fica guardado, e toda referência segue.
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
# 10. O raiz que só monta providers não é a tela
# ----------------------------------------------------------------------


def test_root_that_only_wraps_providers_is_not_the_screen(system):
    """
    Sem roteador interno, o micro frontend mostra uma tela no prefixo do
    `activeWhen`. O componente raiz que só monta `<Provider>` do Redux
    (https://react-redux.js.org/api/provider) em volta do `App` não é ela:
    a tela é o `App`, o primeiro com conteúdo próprio.
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
# 11. O molde de um gerador não é micro frontend
# ----------------------------------------------------------------------


def test_generator_template_is_not_a_microfrontend(system):
    """
    O `package.json` com marcação de modelo (`"<%= name %>"`, sem aspas em
    volta do valor) não é JSON, e o npm não instala o pacote
    (https://docs.npmjs.com/cli/configuring-npm/package-json): os ciclos
    de vida no molde não fazem dele uma unidade.
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
