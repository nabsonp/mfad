"""
Registro de reconstrutores.

É o ponto de extensão do módulo 1: adicionar suporte a outra
tecnologia de micro frontend é escrever uma implementação de
`Reconstructor` e registrá-la aqui. Nenhum outro módulo muda.
"""

from __future__ import annotations

from pathlib import Path

from damfe.application.ports import Reconstructor


_REGISTRY: dict[str, Reconstructor] = {}


def register(reconstructor: Reconstructor) -> Reconstructor:

    _REGISTRY[reconstructor.name] = reconstructor

    return reconstructor


def available() -> list[Reconstructor]:

    return sorted(_REGISTRY.values(), key=lambda item: item.name)


def get(name: str) -> Reconstructor:

    if name not in _REGISTRY:

        known = ", ".join(sorted(_REGISTRY)) or "nenhum"

        raise KeyError(
            f"Framework desconhecido: {name}. Disponíveis: {known}"
        )

    return _REGISTRY[name]


def detect(repository: Path) -> Reconstructor | None:
    """Devolve o primeiro reconstrutor que reconhece o repositório."""

    for reconstructor in available():

        if reconstructor.detect(repository):
            return reconstructor

    return None
