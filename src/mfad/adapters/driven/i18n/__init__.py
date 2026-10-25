"""
Os textos que a ferramenta mostra, em português e em inglês.

Um JSON só, com cada chave nos dois idiomas lado a lado: quem
traduz vê as duas versões juntas, e a página e as regras leem do
mesmo lugar.

Um texto é referido por uma `Ref` — a chave e os valores que entram
nele —, e não pela frase pronta. A página leva as referências e troca
de idioma sem voltar ao Python; o artefato de detecção leva a frase
em português, como sempre, e a referência no `metadata`.

Formato de uma entrada:

- `{"pt": "...", "en": "..."}`, com `{nome}` para cada valor;
- plural: `{"pt": {"one": "...", "other": "..."}, ...}`, escolhido
  pelo valor `n`, ou pelo que `"plural"` nomear;
- um valor que é outra `Ref` (`{"key": ..., "args": ...}`) é
  traduzido antes de entrar.
"""

from __future__ import annotations

import html
import json
from functools import lru_cache
from importlib import resources
from typing import Any

LANGUAGES = ("pt", "en")

DEFAULT = "pt"

#: O rótulo de cada idioma no seletor: o português é o do Brasil.
LABELS = {"pt": "PT-BR", "en": "EN"}

#: Uma referência a texto: `{"key": "hammering.message", "args": {...}}`.
Ref = dict[str, Any]


@lru_cache(maxsize=None)
def texts() -> dict[str, dict]:

    return json.loads(
        resources.files("mfad.adapters.driven.i18n")
        .joinpath("texts.json")
        .read_text(encoding="utf-8")
    )


def ref(key: str, **args: Any) -> Ref:
    """A referência, conferida: chave que não existe é erro aqui, não na página."""

    if key not in texts():
        raise KeyError(f"texto sem tradução: {key}")

    return {"key": key, "args": args}


def fact(label: str, value: Any) -> dict[str, Any]:
    """
    Um dado da detecção, rotulado: a página mostra cada um num campo,
    em vez de uma frase que junta todos.
    """

    return {"label": ref(label), "value": value}


def t(value: Ref | str, language: str = DEFAULT) -> str:
    """A frase no idioma pedido."""

    if isinstance(value, str):
        value = {"key": value, "args": {}}

    entry = texts()[value["key"]]

    args = {
        name: t(item, language) if isinstance(item, dict) and "key" in item else item
        for name, item in (value.get("args") or {}).items()
    }

    template = entry.get(language, entry[DEFAULT])

    if isinstance(template, dict):
        count = args.get(entry.get("plural", "n"))
        template = template["one" if count == 1 else "other"]

    return template.format(**args)


def longest(value: Ref | str) -> str:
    """A versão mais longa, para medir caixa que tem de caber nas duas."""

    return max((t(value, language) for language in LANGUAGES), key=len)


def mark(value: Ref | str, tag: str = "span", attrs: str = "") -> str:
    """
    O texto no idioma padrão, marcado para a página trocar de idioma.

    `data-t` é a chave e `data-a`, os valores; o script refaz a frase
    a partir dos dois.
    """

    return f"<{tag}{attrs}{marker(value)}>{html.escape(t(value))}</{tag}>"


def marker(value: Ref | str, attribute: str | None = None) -> str:
    """
    Só os atributos da marca, para um elemento que o chamador escreve.

    Com `attribute`, o que se traduz é aquele atributo (`placeholder`,
    `title`), não o conteúdo.
    """

    if isinstance(value, str):
        value = {"key": value, "args": {}}

    args = value.get("args") or {}

    return (
        f' data-t="{html.escape(value["key"])}"'
        + (f' data-a="{html.escape(json.dumps(args, ensure_ascii=False))}"' if args else "")
        + (f' data-t-attr="{attribute}"' if attribute else "")
    )
