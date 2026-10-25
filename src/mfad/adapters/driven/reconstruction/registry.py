"""
Registro de reconstrutores.

É o ponto de extensão do módulo 1: adicionar suporte a outra
tecnologia de micro frontend é escrever uma implementação de
`Reconstructor` e registrá-la aqui. Nenhum outro módulo muda.
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


def unsupported(repository: Path) -> str | None:
    """
    A plataforma não suportada, quando ela é o repositório inteiro.

    Pacotes construídos sobre plataforma com integração própria saem
    da varredura (ver `SourceTree.PLATFORMS`). Quando não sobra código
    nenhum, a resposta honesta é "não suportado", não uma reconstrução
    vazia que parece válida.
    """

    from mfad.adapters.driven.reconstruction.ast import SourceTree

    tree = SourceTree(repository)

    if next(tree.source_files(), None) is not None or not tree.skipped:
        return None

    return sorted(tree.skipped.values())[0]


def excluded(repository: Path) -> dict[str, str]:
    """Os pacotes deixados de fora por serem de plataforma não suportada."""

    from mfad.adapters.driven.reconstruction.ast import SourceTree

    tree = SourceTree(repository)

    for _ in tree.source_files():
        pass

    return {tree.relative(path) or ".": platform for path, platform in sorted(tree.skipped.items())}
