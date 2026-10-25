"""As formas de declarar rota no React Router e no @reach/router."""

import textwrap

import pytest

from conftest import by_id, mfe, root_config

from mfad.adapters.driven.reconstruction.ast import AstReader, RouteConstantTable
from mfad.adapters.driven.reconstruction.routers import ReactRouteReader


@pytest.fixture
def routes(tmp_path):
    """Lê as rotas de um trecho de código: `[(componente, rota)]`."""

    def read(code: str):

        path = tmp_path / "routes.jsx"
        path.write_text(textwrap.dedent(code), encoding="utf-8")

        root, source = AstReader().parse(path)

        constants = RouteConstantTable()
        constants.index_file(root, source)
        constants.resolve_pending()

        return [
            (entry.component, entry.route)
            for entry in ReactRouteReader(constants).routes_in(root, source)
        ]

    return read


def test_v6_jsx_routes_nest_relatively(routes):

    assert routes("""
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="account" element={<Layout />}>
            <Route index element={<Overview />} />
            <Route path="orders" element={<Orders />} />
            <Route path="/absolute" element={<Absolute />} />
          </Route>
        </Routes>
    """) == [
        ("Home", "/"),
        ("Layout", "/account"),
        ("Overview", "/account"),
        ("Orders", "/account/orders"),
        ("Absolute", "/absolute"),
    ]


def test_v5_component_render_and_children(routes):

    assert routes("""
        <Switch>
          <Route exact path="/" component={Home} />
          <Route path="/property/:id" render={(props) => <Property {...props} />} />
          <Route path="/static">
            <Static />
          </Route>
        </Switch>
    """) == [
        ("Home", "/"),
        ("Property", "/property/:id"),
        ("Static", "/static"),
    ]


def test_data_router_objects(routes):

    assert routes("""
        const router = createBrowserRouter([
          {
            path: "/",
            element: <Root />,
            children: [
              { index: true, element: <Home /> },
              { path: "movie/:id", Component: Movie },
              { path: "search", lazy: () => import("./pages/Search") },
            ],
          },
        ]);
    """) == [
        ("Root", "/"),
        ("Home", "/"),
        ("Movie", "/movie/:id"),
        ("Search", "/search"),
    ]


def test_reach_router_children_of_router(routes):

    assert routes("""
        import { Router } from "@reach/router";

        <Router>
          <Login path="/auth" />
          <Register path="/auth/sign-up" />
          <Dashboard path="dashboard">
            <Settings path="settings" />
          </Dashboard>
          <NotFound default />
        </Router>
    """) == [
        ("Login", "/auth"),
        ("Register", "/auth/sign-up"),
        ("Dashboard", "/dashboard"),
        ("Settings", "/dashboard/settings"),
        ("NotFound", None),
    ]


def test_path_attribute_outside_a_router_is_not_a_route(routes):
    """`<svg><Path path="…"/></svg>` não é rota; sem @reach/router, nada."""

    assert routes("""
        <Icon><Shape path="/m0 0" /></Icon>
    """) == []


def test_angular_route_arrays_are_left_to_the_angular_reader(routes):

    assert routes("""
        const routes = [{ path: "invoices", component: InvoicesComponent }];
    """) == []


def test_v5_routes_become_screens_of_the_unit(system):

    architecture = system(
        {
            **root_config({"@org/property": "/property"}),
            **mfe("property", "@org/property", """
                import { Switch, Route } from "react-router-dom";
                import { PropertyView } from "./views/property-view";
                import { NewProperty } from "./views/new-property";

                export default function Root() {
                  return (
                    <Switch>
                      <Route path="/property/new" component={NewProperty} />
                      <Route path="/property/:id"><PropertyView /></Route>
                    </Switch>
                  );
                }
            """),
            "property/src/views/property-view.js": "export const PropertyView = () => null;",
            "property/src/views/new-property.js": "export const NewProperty = () => null;",
        },
        prefix="@org/",
    )

    screens = sorted((screen.component, screen.route, screen.file) for screen in by_id(architecture, "property").screens)

    assert screens == [
        ("NewProperty", "/property/new", "property/src/views/new-property.js"),
        ("PropertyView", "/property/:id", "property/src/views/property-view.js"),
    ]
