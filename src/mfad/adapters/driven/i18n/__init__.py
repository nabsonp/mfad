"""
The texts the tool shows, in Portuguese and in English.

A single JSON, with each key in both languages side by side: whoever
translates sees both versions together, and the page and the rules
read from the same place.

A text is referred to by a `Ref` (the key and the values that go
into it), not by the finished sentence. The page carries the
references and switches language without going back to Python; the
detection artifact carries the sentence in the default language
(English) and the reference in `metadata`.

Format of an entry:

- `{"pt": "...", "en": "..."}`, with `{name}` for each value;
- plural: `{"pt": {"one": "...", "other": "..."}, ...}`, chosen
  by the value `n`, or by the one `"plural"` names;
- a value that is another `Ref` (`{"key": ..., "args": ...}`) is
  translated before it goes in.
"""

from __future__ import annotations

import html
import json
from functools import lru_cache
from importlib import resources
from typing import Any

LANGUAGES = ("pt", "en")

DEFAULT = "en"

#: The label of each language in the selector: Portuguese is Brazilian Portuguese.
LABELS = {"pt": "PT-BR", "en": "EN"}

#: A reference to a text: `{"key": "hammering.message", "args": {...}}`.
Ref = dict[str, Any]


@lru_cache(maxsize=None)
def texts() -> dict[str, dict]:

    return json.loads(
        resources.files("mfad.adapters.driven.i18n")
        .joinpath("texts.json")
        .read_text(encoding="utf-8")
    )


def ref(key: str, **args: Any) -> Ref:
    """The reference, checked: a key that does not exist is an error here, not on the page."""

    if key not in texts():
        raise KeyError(f"text without translation: {key}")

    return {"key": key, "args": args}


def fact(label: str, value: Any) -> dict[str, Any]:
    """
    A detection datum, labeled: the page shows each one in its own
    field, instead of a sentence that joins them all.
    """

    return {"label": ref(label), "value": value}


def t(value: Ref | str, language: str = DEFAULT) -> str:
    """The sentence in the requested language."""

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
    """The longest version, to size a box that has to fit both."""

    return max((t(value, language) for language in LANGUAGES), key=len)


def mark(value: Ref | str, tag: str = "span", attrs: str = "") -> str:
    """
    The text in the default language, marked for the page to switch
    language.

    `data-t` is the key and `data-a` the values; the script rebuilds
    the sentence from the two.
    """

    return f"<{tag}{attrs}{marker(value)}>{html.escape(t(value))}</{tag}>"


def marker(value: Ref | str, attribute: str | None = None) -> str:
    """
    Only the marker attributes, for an element the caller writes.

    With `attribute`, what gets translated is that attribute
    (`placeholder`, `title`), not the content.
    """

    if isinstance(value, str):
        value = {"key": value, "args": {}}

    args = value.get("args") or {}

    return (
        f' data-t="{html.escape(value["key"])}"'
        + (f' data-a="{html.escape(json.dumps(args, ensure_ascii=False))}"' if args else "")
        + (f' data-t-attr="{attribute}"' if attribute else "")
    )
