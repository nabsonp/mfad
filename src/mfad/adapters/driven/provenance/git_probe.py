"""
Provenance read from git.

The analysis runs both on a single repository and on a folder with
several clones, which is how `mfad setup` is used. That is why the
probe looks for repositories up to two levels below the root, and
stops descending as soon as it finds one: a submodule or a nested
`.git` is not a unit of analysis.

Nothing here may fail the analysis. Without git installed, without a
repository, or with the command returning an error, the result is
simply a poorer provenance.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from mfad.application.ports import SourceProbe
from mfad.domain import SourceRepository


#: Maximum search depth, counted from the root.
MAX_DEPTH = 2

IGNORED = {"node_modules", "dist", "build", ".next", "coverage"}

#: Credential embedded in the origin URL, in the form
#: `scheme://user:password@host/...`.
#:
#: Cloning with a token in the URL is common, and the remote is stored in
#: `.git/config`. Copying it into the artifact would publish the credential:
#: the output is versioned together with the dissertation.
CREDENTIAL = re.compile(r"(?<=://)[^/@]+@")

TIMEOUT = 10


class GitSourceProbe(SourceProbe):

    def describe(self, root: Path) -> list[SourceRepository]:

        root = root.resolve()

        return sorted(
            (
                self._describe_one(repository, root)
                for repository in self._repositories(root, root, 0)
            ),
            key=lambda source: source.path,
        )

    # ------------------------------------------------------------------

    @classmethod
    def _repositories(
        cls,
        directory: Path,
        root: Path,
        depth: int,
    ) -> list[Path]:

        if (directory / ".git").exists():
            return [directory]

        if depth >= MAX_DEPTH:
            return []

        try:
            entries = sorted(directory.iterdir())
        except OSError:
            return []

        found: list[Path] = []

        for entry in entries:

            if not entry.is_dir() or entry.name in IGNORED:
                continue

            if entry.name.startswith(".") and entry.name != ".git":
                continue

            found.extend(cls._repositories(entry, root, depth + 1))

        return found

    @classmethod
    def _describe_one(cls, repository: Path, root: Path) -> SourceRepository:

        try:
            relative = str(repository.relative_to(root))
        except ValueError:
            relative = repository.name

        return SourceRepository(
            path="." if relative == "." else relative,
            remote=cls._sanitize(
                cls._git(repository, "config", "--get", "remote.origin.url")
            ),
            commit=cls._git(repository, "rev-parse", "HEAD"),
            dirty=bool(cls._git(repository, "status", "--porcelain")),
        )

    @staticmethod
    def _sanitize(remote: str) -> str:

        return CREDENTIAL.sub("", remote)

    @staticmethod
    def _git(repository: Path, *arguments: str) -> str:

        try:
            completed = subprocess.run(
                ["git", "-C", str(repository), *arguments],
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return ""

        if completed.returncode != 0:
            return ""

        return completed.stdout.strip()
