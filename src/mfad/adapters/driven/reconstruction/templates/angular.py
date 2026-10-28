"""
Angular template composition.

Written from the documentation of `@Component` and selectors at
https://angular.dev/guide/components/selectors, not from any particular
repository.

In React, the screen that renders a component imports it: the JSX uses
the identifier, and the identifier comes from an import. Not in Angular.
The screen writes `<app-tabela>` in the template, and what links the
selector to the class is the `NgModule` that declares both. The
screen's `.ts` does not import the child, and following only imports
leaves out everything it renders, along with the services those
children use.

This module returns that link: for a component, the files of the
components and directives its template uses. Reachability treats this
as one more import.

The boundary is the same as for relative imports: the package. A
selector only matches a component declared in the same package; one
from an external library (`<mat-table>`) is not the unit's code.
"""

from __future__ import annotations

import re

from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Node

from mfad.adapters.driven.reconstruction.ast import AstReader


#: The decorators that declare a selector. Directives are included because
#: they are also code the screen brings to life when it uses the attribute.
DECORATORS = ("Component", "Directive")

#: `<app-tabela`: the element name, in the template.
_TAG = re.compile(r"<([a-zA-Z][\w-]*)([^>]*)>?", re.S)

#: An attribute inside the opening tag, in its binding forms:
#: `appX`, `[appX]`, `(appX)`, `[(appX)]`, `*appX`.
_ATTRIBUTE = re.compile(r"(?:^|\s)[\[(*]*([a-zA-Z_][\w-]*)")

#: Parts of a selector: the element at the start and the attributes
#: in brackets. Classes and `:not(...)` do not reliably identify a use
#: and are left out.
_SELECTOR_ELEMENT = re.compile(r"^([a-zA-Z][\w-]*)")
_SELECTOR_ATTRIBUTE = re.compile(r"\[([\w-]+)")


@dataclass
class _Declaration:
    """What a file declares: selectors and the template it uses."""

    elements: set[str] = field(default_factory=set)
    attributes: set[str] = field(default_factory=set)
    template: str = ""


class AngularTemplates:
    """Components used by each component's template."""

    def __init__(self, reader: AstReader, files: list[Path]):

        self.reader = reader

        #: file → what it declares
        self._declared: dict[Path, _Declaration] = {}

        #: package → selector → files
        self._elements: dict[Path, dict[str, set[Path]]] = {}
        self._attributes: dict[Path, dict[str, set[Path]]] = {}

        self._packages: dict[Path, Path] = {}

        for file_path in files:

            declaration = self._declaration(file_path)

            if declaration is None:
                continue

            self._declared[file_path] = declaration

            package = self._package(file_path)

            for name in declaration.elements:
                self._elements.setdefault(package, {}).setdefault(
                    name, set()
                ).add(file_path)

            for name in declaration.attributes:
                self._attributes.setdefault(package, {}).setdefault(
                    name, set()
                ).add(file_path)

    def used_by(self, file_path: Path) -> set[Path]:
        """The files this component's template brings to life."""

        declaration = self._declared.get(file_path)

        if declaration is None or not declaration.template:
            return set()

        package = self._package(file_path)

        elements = self._elements.get(package, {})
        attributes = self._attributes.get(package, {})

        found: set[Path] = set()

        for tag in _TAG.finditer(declaration.template):

            found.update(elements.get(tag.group(1), ()))

            if attributes:
                for attribute in _ATTRIBUTE.finditer(tag.group(2)):
                    found.update(attributes.get(attribute.group(1), ()))

        found.discard(file_path)

        return found

    # ------------------------------------------------------------------

    def _declaration(self, file_path: Path) -> _Declaration | None:

        if file_path.suffix != ".ts":
            return None

        # The reader already holds the tree and text of every file since the
        # context scan; reading from disk again cost minutes on a large
        # repository.
        try:
            root, source = self.reader.parse(file_path)
        except Exception:
            return None

        if not any(f"@{name}".encode() in source for name in DECORATORS):
            return None

        found: _Declaration | None = None

        for decorator in AstReader.find_all(root, "decorator"):

            fields = self._metadata(decorator, source)

            if fields is None:
                continue

            found = found or _Declaration()

            self._read_selector(fields.get("selector"), source, found)

            found.template += self._template(fields, source, file_path)

        return found

    @staticmethod
    def _metadata(decorator: Node, source: bytes) -> dict[str, Node] | None:
        """The fields of `@Component({...})`, if it is one of those."""

        for call in decorator.named_children:

            if call.type != "call_expression":
                continue

            function = call.child_by_field_name("function")

            if not function or AstReader.text(function, source) not in DECORATORS:
                return None

            arguments = call.child_by_field_name("arguments")

            if not arguments:
                return None

            for argument in arguments.named_children:

                if argument.type != "object":
                    continue

                fields: dict[str, Node] = {}

                for pair in argument.named_children:

                    if pair.type != "pair":
                        continue

                    key = pair.child_by_field_name("key")
                    value = pair.child_by_field_name("value")

                    if key and value:
                        fields[
                            AstReader.strip_quotes(AstReader.text(key, source))
                        ] = value

                return fields

        return None

    @staticmethod
    def _read_selector(
        node: Node | None,
        source: bytes,
        found: _Declaration,
    ) -> None:
        """
        `app-x`, `[appX]`, `button[appX]` and lists `a, b`.

        An element selector with an attribute (`button[appX]`) is stored
        by the attribute: `button` alone would match every button.
        """

        if node is None or node.type not in ("string", "template_string"):
            return

        selector = AstReader.strip_quotes(AstReader.text(node, source))

        for part in selector.split(","):

            part = re.sub(r":not\([^)]*\)", "", part).strip()

            attributes = _SELECTOR_ATTRIBUTE.findall(part)

            if attributes:
                found.attributes.update(attributes)
                continue

            element = _SELECTOR_ELEMENT.match(part)

            if element:
                found.elements.add(element.group(1))

    @staticmethod
    def _template(
        fields: dict[str, Node],
        source: bytes,
        file_path: Path,
    ) -> str:
        """The inline template or the `templateUrl` file."""

        inline = fields.get("template")

        if inline is not None and inline.type in ("string", "template_string"):
            return AstReader.strip_quotes(AstReader.text(inline, source))

        url = fields.get("templateUrl")

        if url is None or url.type not in ("string", "template_string"):
            return ""

        target = (
            file_path.parent / AstReader.strip_quotes(AstReader.text(url, source))
        )

        try:
            return target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def _package(self, file_path: Path) -> Path:
        """The nearest directory with `package.json`: the boundary."""

        directory = file_path.parent

        if directory in self._packages:
            return self._packages[directory]

        current = directory

        while not (current / "package.json").is_file():

            if current.parent == current:
                current = directory
                break

            current = current.parent

        self._packages[directory] = current

        return current
