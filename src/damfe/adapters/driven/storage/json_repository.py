"""
Persistência em JSON — um arquivo por coleção.

Implementa a porta `ArtifactRepository`. Os comandos não sabem
que existe JSON nem sistema de arquivos: trocar por um banco é
escrever outra implementação da mesma porta.
"""

from __future__ import annotations

import json
from dataclasses import asdict, fields, is_dataclass
from pathlib import Path
from typing import Any

from damfe.domain.detection import AntiPatternDetection
from damfe.domain import (
    ApiCall,
    Domain,
    CodeSize,
    Communication,
    MicroFrontend,
    ArtifactSet,
    Fragment,
    FragmentImport,
    Navigation,
    RenderSite,
    Screen,
    SourceLocation,
    StateAccess,
)
from damfe.application.ports import ArtifactRepository


MICROFRONTENDS = "microfrontends.json"
FRAGMENT_IMPORTS = "fragment_imports.json"
NAVIGATIONS = "navigations.json"
COMMUNICATIONS = "communications.json"
API_CALLS = "api_calls.json"
MANIFEST = "manifest.json"
STATE_ACCESSES = "state_accesses.json"
DOMAINS = "domains.json"
DETECTIONS = "detections.json"


class JsonArtifactRepository(ArtifactRepository):

    def save(self, artifacts: ArtifactSet, destination: Path) -> list[Path]:
        """
        Grava TODAS as coleções, inclusive as vazias.

        Pular a coleção vazia deixaria o arquivo da execução
        anterior no lugar, e a etapa seguinte leria dado que não
        corresponde mais ao código — uma discrepância que não
        levanta erro nenhum e produz resultado plausível.
        """

        destination.mkdir(parents=True, exist_ok=True)

        colecoes = [
            (MICROFRONTENDS, artifacts.microfrontends),
            (FRAGMENT_IMPORTS, artifacts.fragment_imports),
            (NAVIGATIONS, artifacts.navigations),
            (COMMUNICATIONS, artifacts.communications),
            (API_CALLS, artifacts.api_calls),
            (STATE_ACCESSES, artifacts.state_accesses),
            (DOMAINS, artifacts.domains),
        ]

        return [
            self._write(
                destination / MANIFEST,
                {"project": artifacts.project},
            )
        ] + [
            self._write(
                destination / nome,
                [_dump(item) for item in colecao],
            )
            for nome, colecao in colecoes
        ]

    def load(self, source: Path) -> ArtifactSet:

        return ArtifactSet(
            project=(self._read(source / MANIFEST) or {}).get("project", ""),
            microfrontends=[
                _load(MicroFrontend, item)
                for item in self._read(source / MICROFRONTENDS) or []
            ],
            fragment_imports=[
                _load(FragmentImport, item)
                for item in self._read(source / FRAGMENT_IMPORTS) or []
            ],
            navigations=[
                _load(Navigation, item)
                for item in self._read(source / NAVIGATIONS) or []
            ],
            communications=[
                _load(Communication, item)
                for item in self._read(source / COMMUNICATIONS) or []
            ],
            api_calls=[
                _load(ApiCall, item)
                for item in self._read(source / API_CALLS) or []
            ],
            state_accesses=[
                _load(StateAccess, item)
                for item in self._read(source / STATE_ACCESSES) or []
            ],
            domains=[
                _load(Domain, item)
                for item in self._read(source / DOMAINS) or []
            ],
        )

    def save_detections(
        self,
        detections: list[AntiPatternDetection],
        destination: Path,
    ) -> Path:

        if destination.suffix != ".json":
            destination.mkdir(parents=True, exist_ok=True)
            destination = destination / DETECTIONS

        else:
            destination.parent.mkdir(parents=True, exist_ok=True)

        return self._write(
            destination,
            [_dump(item) for item in detections],
        )

    def load_detections(self, source: Path) -> list[AntiPatternDetection]:

        if source.is_dir():
            source = source / DETECTIONS

        return [
            _load(AntiPatternDetection, item)
            for item in self._read(source) or []
        ]

    # ------------------------------------------------------------------

    @staticmethod
    def _write(path: Path, payload: Any) -> Path:

        path.parent.mkdir(parents=True, exist_ok=True)

        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        return path

    @staticmethod
    def _read(path: Path) -> Any:

        if not path.is_file():
            return None

        return json.loads(path.read_text(encoding="utf-8"))


def _dump(value: Any) -> Any:

    return asdict(value) if is_dataclass(value) else value


#: Campos que guardam outra dataclass, POR TIPO — e não por nome de
#: campo. O mesmo nome significa coisas diferentes em entidades
#: diferentes: `MicroFrontend.screens` são telas, `Domain.screens` são
#: identificadores de tela. Um mapa global confundiria os dois.
_NESTED: dict[type, dict[str, type]] = {
    MicroFrontend: {
        "fragments": Fragment,
        "screens": Screen,
        "size": CodeSize,
    },
    FragmentImport: {
        "imported_at": SourceLocation,
        "renders": RenderSite,
    },
    Navigation: {"at": SourceLocation},
    Communication: {
        "produced_at": SourceLocation,
        "consumed_at": SourceLocation,
    },
    ApiCall: {"at": SourceLocation},
    StateAccess: {"at": SourceLocation},
    AntiPatternDetection: {"locations": SourceLocation},
}


def _load(target: type, payload: dict) -> Any:
    """Reconstrói uma dataclass, descendo nos campos aninhados."""

    known = {field.name for field in fields(target)}

    aninhados = _NESTED.get(target, {})

    arguments: dict[str, Any] = {}

    for key, value in payload.items():

        if key not in known:
            continue

        nested = aninhados.get(key)

        if nested and isinstance(value, list):
            arguments[key] = [_load(nested, item) for item in value]

        elif nested and isinstance(value, dict):
            arguments[key] = _load(nested, value)

        else:
            arguments[key] = value

    return target(**arguments)
