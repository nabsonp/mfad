"""
Test utilities.

Each test builds a minimal repository in a temporary folder, with
only the code the rule under test needs to see, and runs the whole
reconstruction over it. The examples are written from each
technology's documentation — not copied from the study's systems —,
so that the test proves the rule and not the shape of a project.
"""

from __future__ import annotations

import json
import textwrap

from pathlib import Path

import pytest

from mfad.composition import Container
from mfad.domain import MicroFrontendArchitecture


def write(root: Path, files: dict[str, str | dict]) -> Path:
    """Writes the files; a dictionary becomes JSON (for `package.json`)."""

    for relative, content in files.items():

        path = root / relative

        path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(content, dict):
            path.write_text(json.dumps(content), encoding="utf-8")
        else:
            path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")

    return root


def reconstruct(
    root: Path,
    framework: str | None = None,
    prefix: str | None = None,
) -> MicroFrontendArchitecture:

    container = Container()

    reconstructor = container.reconstructor(framework, root)

    assert reconstructor is not None, "no extractor recognized the repository"

    # The reconstructors are single instances in the registry: one
    # test's prefix must not leak into the next.
    if hasattr(reconstructor, "organization_prefix"):
        reconstructor.organization_prefix = prefix

    return container.reconstruct(root, None, reconstructor).execute().architecture


@pytest.fixture
def system(tmp_path):
    """`system({...})` writes the files and returns the architecture."""

    def build(files, framework=None, prefix=None):
        write(tmp_path, files)
        return reconstruct(tmp_path, framework, prefix)

    return build


def package(name: str, **dependencies: str) -> dict:
    return {"name": name, "dependencies": dependencies or {"single-spa": "^6.0.0"}}


#: Minimal lifecycle of a single-spa micro frontend in React.
def react_lifecycles(root_component: str = "./root.component") -> str:
    return f"""
        import React from "react";
        import ReactDOM from "react-dom/client";
        import singleSpaReact from "single-spa-react";
        import Root from "{root_component}";

        const lifecycles = singleSpaReact({{ React, ReactDOM, rootComponent: Root }});

        export const {{ bootstrap, mount, unmount }} = lifecycles;
    """


def by_id(architecture: MicroFrontendArchitecture, identifier: str):
    found = architecture.microfrontend(identifier)
    assert found is not None, f"{identifier} is not in the inventory: {[m.id for m in architecture.microfrontends]}"
    return found


def mfe(directory: str, name: str, root: str) -> dict:
    """In the shape `create-single-spa` generates: `src/<org>-<project>.js`."""

    organization, _, project = name.lstrip("@").partition("/")

    return {
        f"{directory}/package.json": package(name),
        f"{directory}/src/{organization}-{project}.js": react_lifecycles(),
        f"{directory}/src/root.component.js": root,
    }


def root_config(applications: dict[str, str], directory: str = "root-config") -> dict:
    """Orchestrator with a literal `registerApplication`: name → `activeWhen`."""

    registrations = "\n".join(
        f"""
        registerApplication({{
          name: "{name}",
          app: () => System.import("{name}"),
          activeWhen: ["{route}"],
        }});"""
        for name, route in applications.items()
    )

    return {
        f"{directory}/package.json": package("@org/root-config"),
        f"{directory}/src/org-root-config.js": (
            'import { registerApplication, start } from "single-spa";\n'
            + textwrap.dedent(registrations)
            + "\nstart();\n"
        ),
    }


ANGULAR_ENTRY = """
    import { platformBrowserDynamic } from "@angular/platform-browser-dynamic";
    import { singleSpaAngular } from "single-spa-angular";
    import { AppModule } from "./app/app.module";

    const lifecycles = singleSpaAngular({
      bootstrapFunction: () => platformBrowserDynamic().bootstrapModule(AppModule),
      template: "<app-root />",
    });

    export const bootstrap = lifecycles.bootstrap;
    export const mount = lifecycles.mount;
    export const unmount = lifecycles.unmount;
"""


def angular_unit(name: str, files: dict[str, str]) -> dict:

    return {
        f"{name}/package.json": package(name, **{"single-spa-angular": "^9"}),
        f"{name}/src/main.single-spa.ts": ANGULAR_ENTRY,
        f"{name}/src/app/app.module.ts": "export class AppModule {}",
        **{f"{name}/src/app/{path}": code for path, code in files.items()},
    }
