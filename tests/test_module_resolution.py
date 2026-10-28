"""
Imports through the `baseUrl` and the `paths` of `tsconfig.json`.

Compiler rules:
https://www.typescriptlang.org/docs/handbook/modules/reference.html#paths
and https://www.typescriptlang.org/tsconfig/#baseUrl. `jsconfig.json`
follows the same format.
"""

from conftest import mfe, root_config, write

from mfad.adapters.driven.reconstruction.ast import ModuleResolver


def test_paths_with_comments_and_extends(tmp_path):

    write(
        tmp_path,
        {
            # Comments and trailing commas are accepted by `tsc`.
            "app/tsconfig.base.json": """
                {
                  // compartilhado
                  "compilerOptions": {
                    "baseUrl": ".",
                    "paths": { "@/*": ["src/*"], "@env": ["src/environments/environment.ts"], },
                  },
                }
            """,
            "app/tsconfig.json": '{ "extends": "./tsconfig.base.json", "compilerOptions": { "strict": true } }',
            "app/src/utils/api.ts": "export const x = 1;",
            "app/src/environments/environment.ts": "export const environment = {};",
            "app/src/services/orders.ts": "export const y = 1;",
            "app/src/pages/Orders.tsx": "",
        },
    )

    importer = tmp_path / "app/src/pages/Orders.tsx"

    assert ModuleResolver.resolve("@/utils/api", importer) == (tmp_path / "app/src/utils/api.ts").resolve()
    assert ModuleResolver.resolve("@env", importer) == (tmp_path / "app/src/environments/environment.ts").resolve()
    # With no matching pattern, `baseUrl` applies.
    assert ModuleResolver.resolve("src/services/orders", importer) == (tmp_path / "app/src/services/orders.ts").resolve()
    # A package is still a package.
    assert ModuleResolver.resolve("react", importer) is None


def test_paths_without_base_url_are_relative_to_the_config(tmp_path):

    write(
        tmp_path,
        {
            "app/jsconfig.json": '{ "compilerOptions": { "paths": { "~/*": ["./src/*"] } } }',
            "app/src/lib/http.js": "",
            "app/src/index.js": "",
        },
    )

    assert ModuleResolver.resolve("~/lib/http", tmp_path / "app/src/index.js") == (
        tmp_path / "app/src/lib/http.js"
    ).resolve()


TSCONFIG = '{ "compilerOptions": { "baseUrl": ".", "paths": { "@/*": ["src/*"], "tracking": ["../checkout/src/track.ts"] } } }'


def test_aliased_imports_are_followed_inside_the_unit(system):
    """The screen imports the service through an alias; the call is the screen's."""

    architecture = system(
        {
            **root_config({"@org/catalog": "/catalog", "@org/checkout": "/checkout"}),
            **mfe("catalog", "@org/catalog", """
                import { BrowserRouter, Routes, Route } from "react-router-dom";
                import Orders from "@/pages/Orders";
                export default function Root() {
                  return (
                    <BrowserRouter>
                      <Routes><Route path="/catalog/orders" element={<Orders />} /></Routes>
                    </BrowserRouter>
                  );
                }
            """),
            "catalog/tsconfig.json": TSCONFIG,
            "catalog/src/pages/Orders.tsx": """
                import { listOrders } from "@/services/orders";
                import { track } from "@org/tracking";
                export default function Orders() { listOrders(); track(); return null; }
            """,
            "catalog/src/services/orders.ts": 'export const listOrders = () => fetch("/orders");',
            # Another micro frontend reached through `paths`: it is a boundary,
            # like a package import, and does not enter the screen's reach.
            **mfe("checkout", "@org/checkout", "export default () => null;"),
            "checkout/src/track.ts": 'export const track = () => fetch("/telemetry");',
        },
        prefix="@org/",
    )

    [call] = [call for call in architecture.api_calls if call.path == "/orders"]

    assert call.screens == ["Orders"]

    [telemetry] = [call for call in architecture.api_calls if call.path == "/telemetry"]

    assert telemetry.microfrontend == "checkout"
    assert "Orders" not in telemetry.screens

    [screen] = architecture.microfrontend("catalog").screens

    assert screen.file == "catalog/src/pages/Orders.tsx"
