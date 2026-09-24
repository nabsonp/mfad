"""Registro de renderizadores — ponto de extensão do módulo 3."""

from __future__ import annotations

from damfe.application.ports import Renderer


_REGISTRY: dict[str, Renderer] = {}


def register(renderer: Renderer) -> Renderer:

    _REGISTRY[renderer.name] = renderer

    return renderer


def available() -> list[Renderer]:

    return sorted(_REGISTRY.values(), key=lambda item: item.name)


def get(name: str) -> Renderer:

    if name not in _REGISTRY:

        known = ", ".join(sorted(_REGISTRY)) or "nenhum"

        raise KeyError(
            f"Formato desconhecido: {name}. Disponíveis: {known}"
        )

    return _REGISTRY[name]
