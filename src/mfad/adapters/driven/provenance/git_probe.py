"""
Procedência lida do git.

A análise roda tanto sobre um repositório único quanto sobre uma
pasta com vários clones — é como o `mfad setup` é usado. Por isso
a sonda procura repositórios até dois níveis abaixo da raiz, e para
de descer assim que encontra um: submódulo e `.git` aninhado não
são unidade de análise.

Nada aqui pode falhar a análise. Sem git instalado, sem repositório
ou com o comando retornando erro, o resultado é simplesmente uma
procedência mais pobre.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from mfad.application.ports import SourceProbe
from mfad.domain import SourceRepository


#: Profundidade máxima da busca, contada a partir da raiz.
MAX_DEPTH = 2

IGNORED = {"node_modules", "dist", "build", ".next", "coverage"}

#: Credencial embutida na URL de origem, no formato
#: `scheme://usuario:senha@host/...`.
#:
#: Clonar com token na URL é comum, e o remote fica gravado no
#: `.git/config`. Copiá-lo para o artefato publicaria a credencial:
#: a saída é versionada junto com a dissertação.
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
