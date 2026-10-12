"""Resolução de especificadores de módulo para arquivos."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=None)
def canonical(path: Path) -> Path:
    """
    O caminho real, sem link simbólico — calculado uma vez por caminho.

    O mesmo arquivo chega pela varredura e pela resolução de import, e
    as duas formas têm de coincidir para servir de chave.
    """

    return Path(os.path.realpath(path))


@dataclass(frozen=True)
class _CompilerPaths:
    """O `baseUrl` e os `paths` que valem para um diretório."""

    base_url: Path | None

    #: padrão -> substituições, já relativas ao diretório certo
    paths: tuple[tuple[str, tuple[Path, ...]], ...]


class ModuleResolver:
    """
    Resolve `./fragments/X` para o arquivo real, seguindo as
    convenções do bundler: extensão implícita e `/index`.

    Especificador sem ponto passa pelo `baseUrl` e pelos `paths` do
    `tsconfig.json` (ou `jsconfig.json`) mais próximo, como o
    compilador do TypeScript faz:
    https://www.typescriptlang.org/docs/handbook/modules/reference.html#paths
    O que não casa com nenhum dos dois é pacote, e fica sem arquivo.
    """

    EXTENSIONS = (".js", ".jsx", ".ts", ".tsx")

    CONFIG_FILES = ("tsconfig.json", "jsconfig.json")

    #: diretório -> configuração que vale para ele
    _configs: dict[Path, _CompilerPaths | None] = {}

    #: Resultados já calculados. Todo arquivo importa `react`, e cada
    #: tentativa pelo `baseUrl` custa uma dúzia de consultas ao disco;
    #: o resultado só depende do caminho-base, ou da configuração e do
    #: especificador.
    _files: dict[Path, Path | None] = {}
    _aliases: dict[tuple[_CompilerPaths, str], Path | None] = {}

    @classmethod
    def resolve(cls, specifier: str, importer: Path) -> Path | None:

        if specifier.startswith("."):
            return cls._file(Path(os.path.normpath(importer.parent / specifier)))

        if not specifier or specifier.startswith("/"):
            return None

        return cls._aliased(specifier, importer)

    @classmethod
    def is_aliased(cls, specifier: str, importer: Path) -> bool:
        """Se o especificador sem ponto é do projeto, não um pacote."""

        return not specifier.startswith(".") and cls.resolve(specifier, importer) is not None

    @classmethod
    def _file(cls, base: Path) -> Path | None:

        if base not in cls._files:
            cls._files[base] = cls._probe(base)

        return cls._files[base]

    @classmethod
    def _probe(cls, base: Path) -> Path | None:

        if base.is_file():
            return base

        # A extensão é ACRESCENTADA ao nome, não posta no lugar do
        # sufixo: `./x.component` é `x.component.ts`. Trocar o
        # sufixo dava `x.ts`, e toda a convenção de nomes do Angular
        # — `.component`, `.service`, `.module` — ficava sem arquivo.
        for extension in cls.EXTENSIONS:

            candidate = base.parent / f"{base.name}{extension}"

            if candidate.is_file():
                return candidate

        # `./x.js` apontando para `x.ts`: o TypeScript em ESM pede a
        # extensão de saída no especificador.
        if base.suffix in cls.EXTENSIONS:

            for extension in cls.EXTENSIONS:

                candidate = base.with_suffix(extension)

                if candidate.is_file():
                    return candidate

        for extension in cls.EXTENSIONS:

            candidate = base / f"index{extension}"

            if candidate.is_file():
                return candidate

        return None

    # ------------------------------------------------------------------
    # baseUrl e paths
    # ------------------------------------------------------------------

    @classmethod
    def _aliased(cls, specifier: str, importer: Path) -> Path | None:

        config = cls._config_for(importer.parent)

        if config is None:
            return None

        key = (config, specifier)

        if key not in cls._aliases:
            cls._aliases[key] = cls._by_config(config, specifier)

        return cls._aliases[key]

    @classmethod
    def _by_config(cls, config: _CompilerPaths, specifier: str) -> Path | None:

        # `paths` antes de `baseUrl`, e entre os padrões o de prefixo
        # mais longo — a regra do compilador.
        for substitutions, captured in cls._matches(config.paths, specifier):

            for target in substitutions:

                found = cls._file(Path(os.path.normpath(str(target).replace("*", captured, 1))))

                if found:
                    return found

        if config.base_url is not None:
            return cls._file(Path(os.path.normpath(config.base_url / specifier)))

        return None

    @staticmethod
    def _matches(
        paths: tuple[tuple[str, tuple[Path, ...]], ...],
        specifier: str,
    ) -> list[tuple[tuple[Path, ...], str]]:

        exact = [targets for pattern, targets in paths if pattern == specifier]

        if exact:
            return [(exact[0], "")]

        found: list[tuple[int, tuple[Path, ...], str]] = []

        for pattern, targets in paths:

            if pattern.count("*") != 1:
                continue

            prefix, _, suffix = pattern.partition("*")

            if (
                specifier.startswith(prefix)
                and specifier.endswith(suffix)
                and len(specifier) >= len(prefix) + len(suffix)
            ):
                captured = specifier[len(prefix):len(specifier) - len(suffix)]
                found.append((len(prefix), targets, captured))

        found.sort(key=lambda item: -item[0])

        return [(targets, captured) for _, targets, captured in found]

    @classmethod
    def _config_for(cls, directory: Path) -> _CompilerPaths | None:
        """O `tsconfig` mais próximo subindo a árvore, já com `extends`."""

        if directory in cls._configs:
            return cls._configs[directory]

        config: _CompilerPaths | None = None

        for name in cls.CONFIG_FILES:

            candidate = directory / name

            if candidate.is_file():
                config = cls._load(candidate, set())
                break

        else:
            parent = directory.parent
            config = cls._config_for(parent) if parent != directory else None

        cls._configs[directory] = config

        return config

    @classmethod
    def _load(cls, file: Path, seen: set[Path]) -> _CompilerPaths | None:

        if file in seen:
            return None

        seen.add(file)

        try:
            data = json.loads(_strip_jsonc(file.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return None

        if not isinstance(data, dict):
            return None

        inherited: _CompilerPaths | None = None

        # `extends` com caminho é arquivo do projeto; com nome de
        # pacote é configuração publicada (`@tsconfig/...`), que não
        # declara `paths` do projeto e fica de fora.
        extends = data.get("extends")

        for parent in extends if isinstance(extends, list) else [extends]:

            if isinstance(parent, str) and parent.startswith("."):

                target = (file.parent / parent).resolve()

                if not target.is_file() and target.with_suffix(".json").is_file():
                    target = target.with_suffix(".json")

                inherited = cls._load(target, seen) or inherited

        options = data.get("compilerOptions") or {}

        base_url = inherited.base_url if inherited else None
        paths = inherited.paths if inherited else ()

        if isinstance(options.get("baseUrl"), str):
            base_url = (file.parent / options["baseUrl"]).resolve()

        if isinstance(options.get("paths"), dict):

            # Sem `baseUrl`, os `paths` são relativos ao próprio arquivo.
            anchor = base_url or file.parent

            paths = tuple(
                (
                    pattern,
                    tuple(anchor / target for target in targets if isinstance(target, str)),
                )
                for pattern, targets in options["paths"].items()
                if isinstance(targets, list)
            )

        if base_url is None and not paths:
            return None

        return _CompilerPaths(base_url=base_url, paths=paths)


_JSONC_TOKENS = re.compile(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*.*?\*/', re.DOTALL)

_TRAILING_COMMAS = re.compile(r',(\s*[}\]])')


def _strip_jsonc(text: str) -> str:
    """O `tsconfig` admite comentário e vírgula no fim; o `json` não."""

    def keep_strings(match: re.Match) -> str:
        token = match.group(0)
        return token if token.startswith('"') else ""

    without_comments = _JSONC_TOKENS.sub(keep_strings, text)

    # Vírgula antes de fechar, só fora das strings.
    parts = []
    last = 0

    for match in re.finditer(r'"(?:\\.|[^"\\])*"', without_comments):
        parts.append(_TRAILING_COMMAS.sub(r"\1", without_comments[last:match.start()]))
        parts.append(match.group(0))
        last = match.end()

    parts.append(_TRAILING_COMMAS.sub(r"\1", without_comments[last:]))

    return "".join(parts)
