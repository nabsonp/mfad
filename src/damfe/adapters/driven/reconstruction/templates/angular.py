"""
Composição por template do Angular.

Escrito a partir da documentação de `@Component` e de seletores em
https://angular.dev/guide/components/selectors — não de repositório
algum.

No React, a tela que renderiza um componente o importa: o JSX usa
o identificador, e o identificador vem de um import. No Angular, não.
A tela escreve `<app-tabela>` no template, e quem liga o seletor à
classe é o `NgModule` que declara os dois. O `.ts` da tela não
importa o filho, e seguir só os imports deixa fora tudo o que ela
renderiza — e os serviços que esses filhos usam.

Este módulo devolve essa ligação: para um componente, os arquivos dos
componentes e diretivas que o template dele usa. O alcance trata isso
como mais um import.

A fronteira é a mesma dos imports relativos: o pacote. Um seletor
só casa com componente declarado no mesmo pacote — o de biblioteca
externa (`<mat-table>`) não é código da unidade.
"""

from __future__ import annotations

import re

from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Node

from damfe.adapters.driven.reconstruction.ast import AstReader


#: Os decoradores que declaram seletor. Diretiva entra porque também
#: é código que a tela põe no ar ao usar o atributo.
DECORATORS = ("Component", "Directive")

#: `<app-tabela` — o nome do elemento, no template.
_TAG = re.compile(r"<([a-zA-Z][\w-]*)([^>]*)>?", re.S)

#: Um atributo dentro da marca de abertura, nas formas de ligação:
#: `appX`, `[appX]`, `(appX)`, `[(appX)]`, `*appX`.
_ATTRIBUTE = re.compile(r"(?:^|\s)[\[(*]*([a-zA-Z_][\w-]*)")

#: Pedaços de um seletor: o elemento no começo e os atributos
#: entre colchetes. Classe e `:not(...)` não identificam um uso
#: com segurança e ficam de fora.
_SELECTOR_ELEMENT = re.compile(r"^([a-zA-Z][\w-]*)")
_SELECTOR_ATTRIBUTE = re.compile(r"\[([\w-]+)")


@dataclass
class _Declaration:
    """O que um arquivo declara: seletores e o template que usa."""

    elements: set[str] = field(default_factory=set)
    attributes: set[str] = field(default_factory=set)
    template: str = ""


class AngularTemplates:
    """Componentes usados pelo template de cada componente."""

    def __init__(self, reader: AstReader, files: list[Path]):

        self.reader = reader

        #: arquivo → o que ele declara
        self._declared: dict[Path, _Declaration] = {}

        #: pacote → seletor → arquivos
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
        """Os arquivos que o template deste componente põe no ar."""

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

        # O leitor já guarda a árvore e o texto de todo arquivo desde a
        # varredura do contexto; ler de novo do disco custava minutos
        # num repositório grande.
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
        """Os campos de `@Component({...})`, se for um deles."""

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
        `app-x`, `[appX]`, `button[appX]` e listas `a, b`.

        Seletor de elemento com atributo (`button[appX]`) é guardado
        pelo atributo: `button` sozinho casaria todo botão.
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
        """O template em linha ou o arquivo de `templateUrl`."""

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
        """O diretório com `package.json` mais próximo — a fronteira."""

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
