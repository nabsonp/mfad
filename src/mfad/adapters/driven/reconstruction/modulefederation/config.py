"""
The federation declaration, wherever it is.

Module Federation has no orchestrator. There is no file that registers
the units of the system, like single-spa's `registerApplication`: each
unit declares itself in its own build file, and the system is what
emerges from those declarations when they are read together.

Three fields matter:

    name       the identity of the unit in the federation network
    exposes    what it publishes, `{ "./Botao": "./src/Botao" }`
    remotes    whom it consumes from, `{ app1: "app1@http://…" }`

The same declaration shows up under several wrappers — webpack, Vite,
Rspack, the Nx wrapper — and all of them take the same object. That is
why the search targets the object, not the bundler.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Node

from mfad.adapters.driven.reconstruction.ast import AstReader

#: How the declaration is built, per bundler.
#:
#: `withModuleFederation` is the Nx wrapper around the webpack plugin,
#: and `federation` is the Vite plugin's. Searching for the plugin
#: name directly would miss both, which is what used to happen.
DECLARATIONS = (
    "ModuleFederationPlugin",
    "withModuleFederation",
    "NxModuleFederationPlugin",
    "federation",
    "moduleFederationPlugin",
)

#: Files that usually hold it.
CONFIG_NAMES = (
    "webpack.config",
    "webpack.prod",
    "webpack.dev",
    "vite.config",
    "rspack.config",
    "module-federation.config",
    "federation.config",
    "next.config",
)


@dataclass
class Federation:
    """What a unit declares about itself and about whom it consumes."""

    name: str
    directory: Path
    declared_in: Path

    #: published path -> internal module
    exposes: dict[str, str] = field(default_factory=dict)

    #: local alias -> remote specifier
    remotes: dict[str, str] = field(default_factory=dict)

    #: declared shared dependencies
    shared: list[str] = field(default_factory=list)


def is_config(path: Path) -> bool:

    return any(path.name.startswith(name) for name in CONFIG_NAMES)


def read(path: Path, root: Node, source: bytes) -> list[Federation]:
    """The federation declarations contained in a file."""

    found = []

    # `new ModuleFederationPlugin({...})` is a `new_expression`, and
    # `withModuleFederation({...})` is a `call_expression`. Both
    # forms appear in the same ecosystem, and searching for only one
    # returned no declaration at all in an entire webpack project.
    # In a file whose name exists only to hold the declaration, the
    # object may be exported with no call around it.
    if path.name.startswith(("module-federation.config", "federation.config")):

        exported = exported_object(root, source)

        if exported is not None:

            federation = _from_object(exported, source, path, root)

            if federation:
                found.append(federation)

    calls = list(AstReader.find_all(root, "call_expression")) + list(
        AstReader.find_all(root, "new_expression")
    )

    for call in calls:

        function = call.child_by_field_name("constructor") or (
            call.child_by_field_name("function")
        )
        arguments = call.child_by_field_name("arguments")

        if not function or not arguments:
            continue

        name = AstReader.text(function, source).split(".")[-1].strip()

        if name not in DECLARATIONS:
            continue

        for child in arguments.named_children:

            # `federation({...})` — the literal is right there.
            if child.type == "object":
                candidate = child

            # `federation(config)` — the literal is elsewhere in the
            # same file. This is the canonical Nx form, and the Vite
            # plugin accepts it too; without resolving the
            # identifier, an entire project reads as if it had no
            # federation at all.
            elif child.type == "identifier":
                candidate = _declared_object(
                    root, AstReader.text(child, source), source
                )

            else:
                candidate = None

            if candidate is None:
                continue

            federation = _from_object(candidate, source, path, root)

            if federation:
                found.append(federation)

    return found


def exported_object(root: Node, source: bytes) -> Node | None:
    """
    The object literal the file exports by default.

    `export default { name, exposes }`, or `export default config`
    with the object declared above. This is how Nx writes
    `module-federation.config.ts`: the file exists only to hold the
    declaration, and there is no call to search inside.
    """

    for node in AstReader.find_all(root, "export_statement"):

        value = node.child_by_field_name("value")

        if value is None:
            continue

        if value.type == "object":
            return value

        if value.type == "identifier":
            resolved = _declared_object(
                root, AstReader.text(value, source), source
            )

            if resolved is not None:
                return resolved

    return None


def _declared_object(root: Node, name: str, source: bytes) -> Node | None:
    """The object literal assigned to `name` in this file."""

    for declarator in AstReader.find_all(root, "variable_declarator"):

        target = declarator.child_by_field_name("name")
        value = declarator.child_by_field_name("value")

        if target is None or value is None:
            continue

        if AstReader.text(target, source) != name:
            continue

        # `const config: ModuleFederationConfig = {...}` — the type
        # annotation sits between the name and the value, and the
        # value is still the object.
        if value.type == "object":
            return value

    return None


def _from_object(
    node: Node,
    source: bytes,
    path: Path,
    root: Node | None = None,
) -> Federation | None:

    fields = _pairs(node, source, root)

    if "name" not in fields:
        return None

    name = AstReader.strip_quotes(
        AstReader.text(fields["name"], source)
    ).strip()

    if not name:
        return None

    return Federation(
        name=name,
        directory=path.parent,
        declared_in=path,
        exposes=_mapping(fields.get("exposes"), source),
        remotes=_mapping(fields.get("remotes"), source),
        shared=sorted(_mapping(fields.get("shared"), source)),
    )


def _pairs(
    node: Node,
    source: bytes,
    root: Node | None = None,
) -> dict[str, Node]:

    found = {}

    for pair in node.named_children:

        # `federation({ ...remoteConfig })` — the literal exists, but
        # what matters is in the object spread inside it. Without
        # resolving it, the `name` field does not show up and the
        # declaration is discarded as if it were not one.
        if pair.type == "spread_element" and root is not None:

            for child in pair.named_children:

                if child.type != "identifier":
                    continue

                target = _declared_object(
                    root, AstReader.text(child, source), source
                )

                if target is not None:
                    found.update(_pairs(target, source, root))

            continue

        if pair.type != "pair":
            continue

        key_node = pair.child_by_field_name("key")
        value_node = pair.child_by_field_name("value")

        if key_node and value_node:
            found[
                AstReader.strip_quotes(AstReader.text(key_node, source))
            ] = value_node

    return found


def _mapping(node: Node | None, source: bytes) -> dict[str, str]:
    """
    A field that is a map, or a list, or neither.

    `exposes` and `remotes` are objects; `shared` is usually an object
    but also appears as a list of names. A field built in a variable
    returns empty: resolving it would require evaluating the module.
    """

    if node is None:
        return {}

    if node.type == "array":
        return {
            AstReader.strip_quotes(AstReader.text(child, source)): ""
            for child in node.named_children
            if child.type == "string"
        }

    if node.type != "object":
        return {}

    found = {}

    for key, value in _pairs(node, source).items():

        text = AstReader.text(value, source)

        found[key] = (
            AstReader.strip_quotes(text)
            if value.type == "string"
            else ""
        )

    return found


def package_name(directory: Path) -> str | None:
    """The name declared in that directory's `package.json`."""

    try:
        manifest = json.loads(
            (directory / "package.json").read_text(encoding="utf-8")
        )
    except Exception:
        return None

    return manifest.get("name")
