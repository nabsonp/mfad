"""
Imports pelo `baseUrl` e pelos `paths` do `tsconfig.json`.

Regras do compilador:
https://www.typescriptlang.org/docs/handbook/modules/reference.html#paths
e https://www.typescriptlang.org/tsconfig/#baseUrl. O `jsconfig.json`
segue o mesmo formato.
"""

from conftest import mfe, root_config, write

from mfad.adapters.driven.reconstruction.ast import ModuleResolver


def test_paths_with_comments_and_extends(tmp_path):

    write(
        tmp_path,
        {
            # Comentário e vírgula no fim são aceitos pelo `tsc`.
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
    # Sem padrão que case, vale o `baseUrl`.
    assert ModuleResolver.resolve("src/services/orders", importer) == (tmp_path / "app/src/services/orders.ts").resolve()
    # Pacote continua pacote.
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
    """A tela importa o serviço por apelido; a chamada é dela."""

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
            # Outro micro frontend alcançado pelos `paths`: é fronteira,
            # como um import de pacote, e não entra no alcance da tela.
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
