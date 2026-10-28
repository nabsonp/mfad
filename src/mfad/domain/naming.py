"""
What each micro frontend is called in the artifacts.

The extractor knows the micro frontend by the name the technology
uses to load it: the `name` of `registerApplication` or of
`ModuleFederationPlugin`. Whoever reads the result looks it up by
repository, or by folder within the monorepo, and the registered name
often does not resemble it (`mf-tipo-inscripcion` inside
`sga_cliente_administracion_mf`). The identifier becomes the
directory; the registered name goes to `metadata["registered_name"]`.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from mfad.domain.model import MicroFrontend, MicroFrontendArchitecture


def distinct(microfrontends: list[MicroFrontend]) -> None:
    """
    Units registered with the same name — seven orchestrators, each in
    its own repository, all `@org/root-config` — get the directory
    name right away, before any relation is extracted. Afterwards
    there is no way to tell them apart: everything each one does would
    come out with the same id.
    """

    counts: dict[str, int] = {}

    for item in microfrontends:
        counts[item.id] = counts.get(item.id, 0) + 1

    repeated = [item for item in microfrontends if counts[item.id] > 1 and item.directory]

    if not repeated:
        return

    last = [PurePosixPath(item.directory).name for item in repeated]

    for item, name in zip(repeated, last):
        item.metadata["registered_name"] = item.id
        item.id = name if last.count(name) == 1 else item.directory


def by_directory(architecture: MicroFrontendArchitecture) -> None:
    """Replaces each micro frontend's identifier with its directory's, in every reference."""

    mapping = _names(architecture)

    if not mapping:
        return

    def name(identifier: str) -> str:
        return mapping.get(identifier, identifier)

    for microfrontend in architecture.microfrontends:

        if microfrontend.id in mapping:
            microfrontend.metadata["registered_name"] = microfrontend.id
            microfrontend.id = mapping[microfrontend.id]

        microfrontend.mounts = [name(item) for item in microfrontend.mounts]

        if "remotes" in microfrontend.metadata:
            microfrontend.metadata["remotes"] = [name(item) for item in microfrontend.metadata["remotes"]]

        for item in microfrontend.fragments + microfrontend.screens:
            item.microfrontend = name(item.microfrontend)

    for composition in architecture.compositions:
        composition.consumer = name(composition.consumer)
        composition.provider = name(composition.provider)

    for item in architecture.navigations + architecture.communications:
        item.source = name(item.source)
        item.target = name(item.target)

    for item in architecture.api_calls + architecture.state_accesses:
        item.microfrontend = name(item.microfrontend)


def _names(architecture: MicroFrontendArchitecture) -> dict[str, str]:
    """
    Registered name → last segment of the directory. If two
    directories end the same (`a/app` and `b/app`), both get the full
    path; without a directory, the registered name is kept.
    """

    last = {item.id: PurePosixPath(item.directory).name for item in architecture.microfrontends if item.directory}

    counts: dict[str, int] = {}

    for value in last.values():
        counts[value] = counts.get(value, 0) + 1

    chosen = {
        identifier: value if counts[value] == 1 else next(item.directory for item in architecture.microfrontends if item.id == identifier)
        for identifier, value in last.items()
    }

    taken = set(chosen.values())

    # A registered name without a directory that matches another
    # directory's would be ambiguous: whoever does not get renamed cannot collide.
    unchanged = {item.id for item in architecture.microfrontends if item.id not in chosen}

    return {
        identifier: value
        for identifier, value in chosen.items()
        if value != identifier and value not in unchanged and list(chosen.values()).count(value) == 1
    } if taken else {}
