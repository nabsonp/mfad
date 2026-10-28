"""
Bottom-up discovery of units.

The usual path starts from the orchestrator: it reads
`registerApplication` and learns which applications exist. It fails
whenever the registration is not written as a literal in the code — and
that is common in real systems, not an exception:

    applications.forEach(registerApplication)   // single-spa-layout
    System.import(name); mountRootParcel(app)   // parcel + import map

In both cases the applications exist, are in the repository, and the
registration names them nowhere the syntax tree can reach.

Here the question is inverted. A package whose entry module exports the
single-spa lifecycles — `bootstrap`, `mount` and `unmount` — **is** a
micro frontend, wherever it was registered. The contract belongs to the
framework, not to the project, and holds even when nobody registers it
in the analyzed code.
"""

from __future__ import annotations

from pathlib import Path

from mfad.adapters.driven.reconstruction.singlespa.context import (
    Registration,
    ScanContext,
)

#: The three that characterize the unit. `update` is optional in the
#: framework, so requiring it would lose legitimate units.
REQUIRED = frozenset({"bootstrap", "mount", "unmount"})


def by_lifecycles(
    context: ScanContext,
    exports_of,
    taken: set[Path],
    in_scope,
) -> list[Registration]:
    """
    Synthetic registrations for the units found through the lifecycles.

    `taken` holds the DIRECTORIES the top-down discovery has already
    covered. Deduplication is by directory, not by name, because the
    two paths name the unit differently: the registration uses the
    import map specifier, this one uses the `name` from
    `package.json`. Comparing names would let the same unit in twice
    with distinct identities.

    When both find the same unit, the real registration wins — it
    carries `activeWhen` and `customProps`, which the entry file does
    not have.
    """

    found: dict[str, Registration] = {}

    for file_path in context.tree.source_files():

        try:
            root, source = context.reader.parse(file_path)
        except Exception:
            continue

        lifecycles, _ = exports_of(root, source)

        if not REQUIRED.issubset(set(lifecycles)):
            continue

        directory = context.package_dir(file_path).resolve()

        if directory in taken or not _installable(directory):
            continue

        name = _package_name(directory) or directory.name

        if name in found or not in_scope(name):
            continue

        taken.add(directory)

        found[name] = Registration(
            name=name,
            active_when=[],
            specifier=None,
            declared_in=file_path,
            active_when_form="absent",
            entrypoint=file_path,
        )

    return [found[name] for name in sorted(found)]


def _package_name(directory: Path) -> str | None:

    import json

    manifest = directory / "package.json"

    if not manifest.is_file():
        return None

    try:
        return json.loads(manifest.read_text(encoding="utf-8")).get("name")
    except Exception:
        return None


def _installable(directory: Path) -> bool:
    """
    Whether the package can be installed and built: without a
    `package.json` the directory counts, but a `package.json` that is
    not JSON (a generator's template, with `"name": "<%= name %>"`) is
    rejected by npm
    (https://docs.npmjs.com/cli/configuring-npm/package-json). It is a
    micro frontend template, not one.
    """

    import json

    manifest = directory / "package.json"

    if not manifest.is_file():
        return True

    try:
        json.loads(manifest.read_text(encoding="utf-8"))
    except Exception:
        return False

    return True
