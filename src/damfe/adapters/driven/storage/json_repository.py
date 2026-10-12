"""
Persistência em JSON — um arquivo por coleção.

Implementa a porta `ArtifactRepository`. Os comandos não sabem
que existe JSON nem sistema de arquivos: trocar por um banco é
escrever outra implementação da mesma porta.
"""

from __future__ import annotations

import json
from dataclasses import asdict, fields, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from damfe.domain.detection import AntiPatternDetection
from damfe.domain import (
    ApiCall,
    CodeSize,
    Communication,
    MicroFrontend,
    MicroFrontendArchitecture,
    Fragment,
    Provenance,
    Composition,
    Navigation,
    Placement,
    RenderLocation,
    Screen,
    SourceLocation,
    SourceRepository,
    StateAccess,
)
from damfe import __version__
from damfe.application.ports import ArtifactRepository


MICROFRONTENDS = "microfrontends.json"
COMPOSITIONS = "compositions.json"
NAVIGATIONS = "navigations.json"
COMMUNICATIONS = "communications.json"
API_CALLS = "api_calls.json"
MANIFEST = "manifest.json"
STATE_ACCESSES = "state_accesses.json"
DETECTIONS = "detections.json"


class JsonArtifactRepository(ArtifactRepository):

    def save(self, architecture: MicroFrontendArchitecture, destination: Path) -> list[Path]:
        """
        Grava TODAS as coleções, inclusive as vazias.

        Pular a coleção vazia deixaria o arquivo da execução
        anterior no lugar, e a etapa seguinte leria dado que não
        corresponde mais ao código — uma discrepância que não
        levanta erro nenhum e produz resultado plausível.
        """

        destination.mkdir(parents=True, exist_ok=True)

        colecoes = [
            (MICROFRONTENDS, architecture.microfrontends),
            (COMPOSITIONS, architecture.compositions),
            (NAVIGATIONS, architecture.navigations),
            (COMMUNICATIONS, architecture.communications),
            (API_CALLS, architecture.api_calls),
            (STATE_ACCESSES, architecture.state_accesses),
        ]

        return [
            self._write(
                destination / MANIFEST,
                self._manifest(architecture, colecoes),
            )
        ] + [
            self._write(
                destination / nome,
                [_dump(item) for item in colecao],
            )
            for nome, colecao in colecoes
        ]

    @staticmethod
    def _manifest(architecture: MicroFrontendArchitecture, colecoes: list[tuple]) -> dict:
        """
        O cabeçalho que torna o conjunto autodescritivo.

        A chave `damfe` é a versão do ESQUEMA; `tool_version` é a da
        ferramenta. Separadas porque corrigir um bug no extrator muda
        a segunda e não a primeira, e uma coleta longa precisa poder
        afirmar que todos os resultados seguem o mesmo esquema.

        O índice de coleções com a contagem fica aqui, e não no
        domínio: nomes de arquivo são detalhe deste adaptador.
        """

        provenance = architecture.provenance

        return {
            "damfe": provenance.schema,
            "tool_version": provenance.tool or __version__,
            "generated_at": (
                provenance.generated_at
                or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            ),
            "project": architecture.project,
            "reconstructor": provenance.reconstructor,
            "sources": [_dump(item) for item in provenance.sources],
            "artifacts": {
                nome.removesuffix(".json"): {
                    "file": nome,
                    "count": len(colecao),
                }
                for nome, colecao in colecoes
            },
        }

    def load(self, source: Path) -> MicroFrontendArchitecture:

        manifest = self._read(source / MANIFEST) or {}

        return MicroFrontendArchitecture(
            project=manifest.get("project", ""),
            provenance=_provenance(manifest),
            microfrontends=[
                _load(MicroFrontend, item)
                for item in self._read(source / MICROFRONTENDS) or []
            ],
            compositions=[
                _load(Composition, item)
                for item in self._read(source / COMPOSITIONS) or []
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


def _provenance(manifest: dict) -> Provenance:
    """
    Lê o cabeçalho, tolerando artefato anterior ao versionamento.

    Manifesto sem a chave `damfe` é de uma execução antes do
    esquema 1.0.0. Vale mais devolver procedência vazia e seguir do
    que recusar o arquivo: quem precisa da revisão exata checa o
    campo e encontra vazio.
    """

    return Provenance(
        schema=manifest.get("damfe", ""),
        tool=manifest.get("tool_version", ""),
        generated_at=manifest.get("generated_at", ""),
        reconstructor=manifest.get("reconstructor", ""),
        sources=[
            _load(SourceRepository, item)
            for item in manifest.get("sources") or []
        ],
    )


def _dump(value: Any) -> Any:

    return asdict(value) if is_dataclass(value) else value


#: Campos que guardam outra dataclass, POR TIPO — e não por nome de
#: campo. O mesmo nome significa coisas diferentes em entidades
#: diferentes: `MicroFrontend.screens` são telas, `RenderLocation.screens`
#: são identificadores de tela. Um mapa global confundiria os dois.
_NESTED: dict[type, dict[str, type]] = {
    MicroFrontend: {
        "fragments": Fragment,
        "screens": Screen,
        "size": CodeSize,
    },
    Composition: {
        "imported_at": SourceLocation,
        "renders": RenderLocation,
    },
    Navigation: {"at": SourceLocation, "on": Placement},
    Communication: {
        "produced_at": SourceLocation,
        "consumed_at": SourceLocation,
        "produced_on": Placement,
        "consumed_on": Placement,
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
