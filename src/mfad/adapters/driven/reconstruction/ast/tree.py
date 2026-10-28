"""Source file scanning with directory pruning."""

from __future__ import annotations

import json

from pathlib import Path
from typing import Iterator

from mfad.adapters.driven.reconstruction.ast.reader import AstReader


class SourceTree:
    """
    Walks the source files of a repository.

    Pruning happens on the way down — ignored directories are never
    opened. This matters: `rglob` descends into the whole
    `node_modules` before discarding it, and the difference is minutes
    versus seconds on a real repository.
    """

    IGNORED_DIRECTORIES = {
        "node_modules",
        "dist",
        "build",
        ".git",
        ".next",
        "coverage",
        "__pycache__",
        # Tests. Test code is not mounted at runtime: a
        # `localStorage.setItem` in a `.spec.ts` couples nothing, and
        # a screen declared only in a test does not exist in the system.
        "__tests__",
        "__mocks__",
        "cypress",
        "e2e",
    }

    #: Test file markers between the name and the extension —
    #: `x.spec.ts`, `auth.guard.spec.ts`, `x.test.jsx`. Convention of
    #: Jest, Vitest, Karma and Jasmine.
    TEST_MARKERS = ("spec", "test")

    #: Micro frontend platforms with their own integration, which no
    #: reconstructor reads: dependency that identifies them → name.
    #:
    #: They use single-spa or Module Federation under the hood, so an
    #: extractor would recognize them — and return a misleading
    #: inventory: the framework registers the applications at
    #: runtime, from its own manifests (`routes.json` in OpenMRS,
    #: plugins in Open edX), and what is left in the code is the
    #: framework's machinery, not the system.
    PLATFORMS = {
        "@openmrs/esm-framework": "OpenMRS 3 (esm-framework)",
        "@edx/frontend-platform": "Open edX (frontend-platform)",
        "@openedx/frontend-platform": "Open edX (frontend-platform)",
    }

    #: The packages that ARE the platform — the framework vendored in a
    #: monorepo does not depend on itself, and would escape the cut.
    PLATFORM_PACKAGES = {
        "@openmrs/esm-": "OpenMRS 3 (esm-framework)",
        "@edx/frontend-platform": "Open edX (frontend-platform)",
        "@openedx/frontend-platform": "Open edX (frontend-platform)",
    }

    def __init__(self, root: Path):
        self.root = root

        #: package → platform, for the ones that were left out
        self.skipped: dict[Path, str] = {}

        self._platform: dict[Path, str | None] = {}

    def source_files(self) -> Iterator[Path]:

        for path in self._walk():

            if path.suffix in AstReader.SUPPORTED_EXTENSIONS:
                yield path

    def markup_files(self) -> Iterator[Path]:
        """HTML and templates, where the declarative layout lives."""

        for path in self._walk():

            if path.suffix in (".html", ".ejs", ".htm"):
                yield path

    def manifests(self, name: str = "package.json") -> Iterator[Path]:

        for path in self._walk():

            if path.name == name:
                yield path

    def _walk(self) -> Iterator[Path]:

        stack = [self.root]

        while stack:

            directory = stack.pop()

            try:
                entries = list(directory.iterdir())
            except OSError:
                continue

            if self._platform_of(directory):
                continue

            for path in entries:

                if path.is_dir():

                    if path.name in self.IGNORED_DIRECTORIES:
                        continue

                    stack.append(path)

                elif not self.is_test(path):
                    yield path

    def _platform_of(self, directory: Path) -> str | None:
        """
        The unsupported platform the package is built on.

        Such a package is left entirely out of the scan, like tests and
        `node_modules`: what it holds is platform integration, which no
        extractor reads correctly. The rest of the repository goes on — a
        system may have an OpenMRS module next to ordinary units.
        """

        if directory in self._platform:
            return self._platform[directory]

        found = None

        manifest_file = directory / "package.json"

        if manifest_file.is_file():

            try:
                manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            except Exception:
                manifest = {}

            name = manifest.get("name") or ""

            declared = {
                **(manifest.get("dependencies") or {}),
                **(manifest.get("devDependencies") or {}),
                **(manifest.get("peerDependencies") or {}),
            }

            found = next(
                (platform for prefix, platform in self.PLATFORM_PACKAGES.items() if name.startswith(prefix)),
                None,
            ) or next(
                (platform for dependency, platform in self.PLATFORMS.items() if dependency in declared),
                None,
            )

        self._platform[directory] = found

        if found:
            self.skipped[directory] = found

        return found

    @classmethod
    def is_test(cls, path: Path) -> bool:
        """`x.spec.ts` and `x.test.js` are tests; `spec.ts` alone is not."""

        middle = path.name.split(".")[1:-1]

        return any(part in cls.TEST_MARKERS for part in middle)

    def relative(self, path: Path) -> str:

        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)
