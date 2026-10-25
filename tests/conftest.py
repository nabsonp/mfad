"""
Utilitários dos testes.

Cada teste monta um repositório mínimo numa pasta temporária, com
só o código que a regra em teste precisa ver, e roda a reconstrução
inteira sobre ele. Os exemplos são escritos a partir da documentação
de cada tecnologia — não copiados dos sistemas do estudo —, para que
o teste prove a regra e não a forma de um projeto.
"""

from __future__ import annotations

import json
import textwrap

from pathlib import Path

import pytest

from mfad.composition import Container
from mfad.domain import MicroFrontendArchitecture


def write(root: Path, files: dict[str, str | dict]) -> Path:
    """Grava os arquivos; dicionário vira JSON (para `package.json`)."""

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

    assert reconstructor is not None, "nenhum extrator reconheceu o repositório"

    # Os reconstrutores são instâncias únicas no registro: o prefixo
    # de um teste não pode vazar para o próximo.
    if hasattr(reconstructor, "organization_prefix"):
        reconstructor.organization_prefix = prefix

    return container.reconstruct(root, None, reconstructor).execute().architecture


@pytest.fixture
def system(tmp_path):
    """`system({...})` grava os arquivos e devolve a arquitetura."""

    def build(files, framework=None, prefix=None):
        write(tmp_path, files)
        return reconstruct(tmp_path, framework, prefix)

    return build


def package(name: str, **dependencies: str) -> dict:
    return {"name": name, "dependencies": dependencies or {"single-spa": "^6.0.0"}}


#: Ciclo de vida mínimo de um micro frontend single-spa em React.
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
    assert found is not None, f"{identifier} não está no inventário: {[m.id for m in architecture.microfrontends]}"
    return found


def mfe(directory: str, name: str, root: str) -> dict:
    """Na forma que o `create-single-spa` gera: `src/<org>-<projeto>.js`."""

    organization, _, project = name.lstrip("@").partition("/")

    return {
        f"{directory}/package.json": package(name),
        f"{directory}/src/{organization}-{project}.js": react_lifecycles(),
        f"{directory}/src/root.component.js": root,
    }


def root_config(applications: dict[str, str], directory: str = "root-config") -> dict:
    """Orquestrador com `registerApplication` literal: nome → `activeWhen`."""

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
