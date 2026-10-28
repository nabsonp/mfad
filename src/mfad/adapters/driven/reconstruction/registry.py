"""
Registry of reconstructors.

This is the extension point of module 1: adding support for another
micro frontend technology means writing an implementation of
`Reconstructor` and registering it here. No other module changes.
"""

from __future__ import annotations

from pathlib import Path

from mfad.application.ports import Reconstructor




_REGISTRY: dict[str, Reconstructor] = {}


def register(reconstructor: Reconstructor) -> Reconstructor:

    _REGISTRY[reconstructor.name] = reconstructor

    return reconstructor


def available() -> list[Reconstructor]:

    return sorted(_REGISTRY.values(), key=lambda item: item.name)


def get(name: str) -> Reconstructor:

    if name not in _REGISTRY:

        known = ", ".join(sorted(_REGISTRY)) or "none"

        raise KeyError(
            f"Unknown framework: {name}. Available: {known}"
        )

    return _REGISTRY[name]


def detect(repository: Path) -> Reconstructor | None:
    """Return the first reconstructor that recognizes the repository."""

    for reconstructor in available():

        if reconstructor.detect(repository):
            return reconstructor

    return None


def unsupported(repository: Path) -> str | None:
    """
    The unsupported platform, when it makes up the whole repository.

    Packages built on a platform with its own integration are left out
    of the scan (see `SourceTree.PLATFORMS`). When no code is left at
    all, the honest answer is "unsupported", not an empty reconstruction
    that looks valid.
    """

    from mfad.adapters.driven.reconstruction.ast import SourceTree

    tree = SourceTree(repository)

    if next(tree.source_files(), None) is not None or not tree.skipped:
        return None

    return sorted(tree.skipped.values())[0]


def excluded(repository: Path) -> dict[str, str]:
    """The packages left out because they belong to an unsupported platform."""

    from mfad.adapters.driven.reconstruction.ast import SourceTree

    tree = SourceTree(repository)

    for _ in tree.source_files():
        pass

    return {tree.relative(path) or ".": platform for path, platform in sorted(tree.skipped.items())}
