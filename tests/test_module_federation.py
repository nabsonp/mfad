"""
Module Federation: what the host loads and what only runs standalone.

Configuration in the shape of the plugin's documentation:
https://webpack.js.org/plugins/module-federation-plugin/
"""

from conftest import by_id


def federation(name: str, exposes: dict[str, str] | None = None, remotes: dict[str, str] | None = None) -> str:

    def literal(entries):
        return "{" + ", ".join(f'"{key}": "{value}"' for key, value in (entries or {}).items()) + "}"

    return f"""
        const {{ ModuleFederationPlugin }} = require("webpack").container;
        module.exports = {{
          plugins: [
            new ModuleFederationPlugin({{
              name: "{name}",
              filename: "remoteEntry.js",
              exposes: {literal(exposes)},
              remotes: {literal(remotes)},
            }}),
          ],
        }};
    """


SYSTEM = {
    "host/package.json": {"name": "host"},
    "host/webpack.config.js": federation(
        "host",
        remotes={"pharmacy": "pharmacy@http://x/remoteEntry.js", "billing": "billing@http://x/remoteEntry.js", "library": "library@http://x/remoteEntry.js"},
    ),
    "host/src/App.jsx": """
        import React, { lazy } from "react";
        import { Routes, Route } from "react-router-dom";
        const Pharmacy = lazy(() => import("pharmacy/Pharmacy"));
        const Billing = lazy(() => import("billing/Billing"));
        export default function App() {
          return (
            <Routes>
              <Route path="/pharmacy" element={<Pharmacy />} />
              <Route path="/billing" element={<Billing />} />
            </Routes>
          );
        }
    """,
    "library/package.json": {"name": "library"},
    "library/webpack.config.js": federation("library", exposes={"./ThemeProvider": "./src/ThemeProvider.jsx"}),
    "library/src/ThemeProvider.jsx": "export default function ThemeProvider({ children }) { return children; }",
}


def remote(name: str, page: str, page_code: str) -> dict:
    """A remote with the published page and the `main.jsx` for when it runs standalone."""

    return {
        f"{name}/package.json": {"name": name},
        f"{name}/webpack.config.js": federation(
            name,
            exposes={f"./{page}": f"./src/{page}.jsx"},
            remotes={"library": "library@http://x/remoteEntry.js"},
        ),
        f"{name}/src/{page}.jsx": page_code,
        # Only runs in development, with the remote opened standalone.
        f"{name}/src/main.jsx": f"""
            import {{ createRoot }} from "react-dom/client";
            import ThemeProvider from "library/ThemeProvider";
            import {page} from "./{page}";
            createRoot(document.getElementById("root")).render(<ThemeProvider><{page} /></ThemeProvider>);
        """,
    }


def test_import_only_in_the_standalone_entry_is_not_a_composition(system):

    architecture = system(
        {
            **SYSTEM,
            **remote("pharmacy", "Pharmacy", "export default function Pharmacy() { return null; }"),
            **remote("billing", "Billing", """
                import ThemeProvider from "library/ThemeProvider";
                export default function Billing() { return <ThemeProvider />; }
            """),
        },
        framework="module-federation",
    )

    pairs = sorted((item.consumer, item.provider, item.fragment) for item in architecture.compositions)

    assert ("pharmacy", "library", "./ThemeProvider") not in pairs
    # On the published page the import is real.
    assert ("billing", "library", "./ThemeProvider") in pairs
    # The host composes the remote pages.
    assert ("host", "pharmacy", "./Pharmacy") in pairs


def test_remote_pages_routed_by_the_host_are_screens_of_the_remote(system):

    architecture = system(
        {
            **SYSTEM,
            **remote("pharmacy", "Pharmacy", "export default function Pharmacy() { return null; }"),
            **remote("billing", "Billing", "export default function Billing() { return null; }"),
        },
        framework="module-federation",
    )

    assert [(screen.component, screen.route) for screen in by_id(architecture, "pharmacy").screens] == [
        ("Pharmacy", "/pharmacy")
    ]
