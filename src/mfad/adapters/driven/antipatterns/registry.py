"""
Registro de regras.

Ponto de extensão do módulo 2. Uma regra nova é uma classe que
implementa `Rule` e uma linha de registro — nada mais no sistema
precisa saber que ela existe.
"""

from __future__ import annotations

from mfad.application.ports import Rule


_REGISTRY: dict[str, Rule] = {}


def register(rule: Rule) -> Rule:

    _REGISTRY[rule.name] = rule

    return rule


def available() -> list[Rule]:

    return sorted(_REGISTRY.values(), key=lambda item: item.name)


def get(name: str) -> Rule:

    if name not in _REGISTRY:

        known = ", ".join(sorted(_REGISTRY)) or "nenhuma"

        raise KeyError(
            f"Regra desconhecida: {name}. Disponíveis: {known}"
        )

    return _REGISTRY[name]
