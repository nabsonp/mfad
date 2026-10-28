"""
Rule registry.

Extension point of module 2. A new rule is a class that implements
`Rule` plus one registration line — nothing else in the system needs
to know it exists.
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

        known = ", ".join(sorted(_REGISTRY)) or "none"

        raise KeyError(
            f"Unknown rule: {name}. Available: {known}"
        )

    return _REGISTRY[name]
