"""
Reachability between files of the same micro frontend.

Service calls rarely live in the screen. The common pattern is the
screen importing a service module, which imports another, which
finally makes the call — and without following that chain the endpoint
is attributed to the file where the call is, which says nothing about
who uses it.

This module solves that by walking the RELATIVE imports, which are the
ones internal to the micro frontend, the `tsconfig` aliases that fall
inside the same package, and — in Angular — the components the
template uses by selector, which the screen renders without importing.
Package imports are left out on purpose: crossing the package boundary
would mean leaving the unit, and it is precisely the boundary that
must be preserved.

The walk is iterative and keeps track of visited nodes, because module
graphs frequently have cycles — two files that import each other are
common and legitimate.
"""

from __future__ import annotations

from pathlib import Path

from mfad.domain import MicroFrontend, Placement
from mfad.adapters.driven.reconstruction.ast import ImportTable, ModuleResolver
from mfad.adapters.driven.reconstruction.singlespa.context import ScanContext


class Reachability:

    def __init__(self, context: ScanContext):

        self.context = context

        self._direct: dict[Path, set[Path]] = {}

        self._closure: dict[Path, set[Path]] = {}

    def reachable_from(self, origin: Path) -> set[Path]:
        """
        The files `origin` reaches, including itself.

        The result is memoized: a screen and a fragment in the same
        folder usually reach almost the same set.
        """

        if origin in self._closure:
            return self._closure[origin]

        seen: set[Path] = set()

        pending = [origin]

        while pending:

            current = pending.pop()

            if current in seen:
                continue

            seen.add(current)

            pending.extend(self._imports_of(current) - seen)

        self._closure[origin] = seen

        return seen

    def _imports_of(self, file_path: Path) -> set[Path]:
        """The files of the same micro frontend that this one imports."""

        if file_path in self._direct:
            return self._direct[file_path]

        found: set[Path] = set()

        try:
            root, source = self.context.reader.parse(file_path)
        except Exception:
            self._direct[file_path] = found
            return found

        package = self.context.package_dir(file_path)

        for record in ImportTable.records(root, source):

            target = ModuleResolver.resolve(record.module, file_path)

            if not target:
                continue

            # A `tsconfig` alias (`@/utils/x`) is an internal project
            # import, but `paths` may also point to a neighboring
            # package in a monorepo — and then it is a boundary, like a
            # package import.
            if not record.module.startswith(".") and package not in target.parents:
                continue

            found.add(target)

        # In Angular the screen does not import what it renders: the
        # template uses the selector. Without this, everything below the screen was left out.
        found |= self.context.templates().used_by(file_path)

        self._direct[file_path] = found

        return found


def placements(
    context: ScanContext,
    microfrontends: list[MicroFrontend],
) -> dict[str, Placement]:
    """
    Relative file → screens and fragments that reach it.

    Inverted on purpose: the extraction finds the instantiation or the
    end of a channel and needs to ask who reaches it, not the other way
    round. Screens and fragments are kept separate because only the
    screen is a place; the fragment is the path through which another
    micro frontend's code reaches a screen.
    """

    reachability = Reachability(context)

    screens: dict[str, set[str]] = {}
    fragments: dict[str, set[str]] = {}

    origins = [
        (screen.file, screen.id, screens)
        for microfrontend in microfrontends
        for screen in microfrontend.screens
    ] + [
        (fragment.file, fragment.id, fragments)
        for microfrontend in microfrontends
        for fragment in microfrontend.fragments
    ]

    for relative, identifier, target in origins:

        if not relative:
            continue

        origin = context.repository / relative

        if not origin.is_file():
            continue

        for reached in reachability.reachable_from(origin):
            target.setdefault(context.relative(reached), set()).add(identifier)

    return {
        path: Placement(
            screens=sorted(screens.get(path, ())),
            fragments=sorted(fragments.get(path, ())),
        )
        for path in set(screens) | set(fragments)
    }


def placement_of(
    found: dict[str, Placement],
    files: list[str],
) -> Placement:
    """The union of the reachability of several files — the several ends of one side."""

    screens: set[str] = set()
    fragments: set[str] = set()

    for file in files:

        item = found.get(file)

        if item:
            screens.update(item.screens)
            fragments.update(item.fragments)

    return Placement(screens=sorted(screens), fragments=sorted(fragments))
