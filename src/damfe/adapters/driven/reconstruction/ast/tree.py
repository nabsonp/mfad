"""Varredura de arquivos-fonte com poda de diretórios."""

from __future__ import annotations

import json

from pathlib import Path
from typing import Iterator

from damfe.adapters.driven.reconstruction.ast.reader import AstReader


class SourceTree:
    """
    Percorre os arquivos-fonte de um repositório.

    A poda acontece na descida — diretórios ignorados nunca
    são abertos. Isso importa: `rglob` desce em `node_modules`
    inteiro antes de descartar, e a diferença é de minutos
    para segundos num repositório real.
    """

    IGNORED_DIRECTORIES = {
        "node_modules",
        "dist",
        "build",
        ".git",
        ".next",
        "coverage",
        "__pycache__",
        # Testes. O código de teste não é montado em execução: um
        # `localStorage.setItem` num `.spec.ts` não acopla ninguém, e
        # uma tela declarada só no teste não existe no sistema.
        "__tests__",
        "__mocks__",
        "cypress",
        "e2e",
    }

    #: Marcas de arquivo de teste entre o nome e a extensão —
    #: `x.spec.ts`, `auth.guard.spec.ts`, `x.test.jsx`. Convenção de
    #: Jest, Vitest, Karma e Jasmine.
    TEST_MARKERS = ("spec", "test")

    #: Plataformas de micro frontend com integração própria, que nenhum
    #: reconstrutor lê: dependência que as identifica → nome.
    #:
    #: Elas usam single-spa ou Module Federation por baixo, e por isso
    #: um extrator as reconheceria — e devolveria um inventário
    #: enganoso: o framework registra as aplicações em tempo de
    #: execução, a partir de manifestos próprios (`routes.json` no
    #: OpenMRS, plugins no Open edX), e o que sobra no código é a
    #: máquina do framework, não o sistema.
    PLATFORMS = {
        "@openmrs/esm-framework": "OpenMRS 3 (esm-framework)",
        "@edx/frontend-platform": "Open edX (frontend-platform)",
        "@openedx/frontend-platform": "Open edX (frontend-platform)",
    }

    #: Os pacotes que SÃO a plataforma — o framework vendorizado num
    #: monorepo não depende de si mesmo, e ficaria de fora do corte.
    PLATFORM_PACKAGES = {
        "@openmrs/esm-": "OpenMRS 3 (esm-framework)",
        "@edx/frontend-platform": "Open edX (frontend-platform)",
        "@openedx/frontend-platform": "Open edX (frontend-platform)",
    }

    def __init__(self, root: Path):
        self.root = root

        #: pacote → plataforma, para os que ficaram de fora
        self.skipped: dict[Path, str] = {}

        self._platform: dict[Path, str | None] = {}

    def source_files(self) -> Iterator[Path]:

        for path in self._walk():

            if path.suffix in AstReader.SUPPORTED_EXTENSIONS:
                yield path

    def markup_files(self) -> Iterator[Path]:
        """HTML e templates, onde mora o layout declarativo."""

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
        A plataforma não suportada sobre a qual o pacote é construído.

        Um pacote assim fica inteiro fora da varredura, como teste e
        `node_modules`: o que ele tem é integração da plataforma, que
        nenhum extrator lê certo. O resto do repositório segue — um
        sistema pode ter um módulo OpenMRS ao lado de unidades comuns.
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
        """`x.spec.ts` e `x.test.js` são teste; `spec.ts` sozinho não."""

        middle = path.name.split(".")[1:-1]

        return any(part in cls.TEST_MARKERS for part in middle)

    def relative(self, path: Path) -> str:

        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)
