"""
Chamadas a serviços externos.

A detecção não depende do framework de micro frontend nem da
organização do projeto. Ela parte de duas âncoras genéricas — a
API da plataforma web e o especificador de import das bibliotecas
cliente — e resolve o caminho com o mesmo avaliador parcial usado
nas rotas.

Projetos costumam embrulhar o cliente HTTP num módulo próprio
(`services/api.js`), e esse módulo pertence ao micro frontend que
o contém — então a aresta `micro frontend → endpoint` sai correta
mesmo sem seguir a indireção.

Para saber qual TELA chama, porém, é preciso segui-la: a chamada
mora no módulo de serviço, não na tela que o usa. O alcance entre
arquivos resolve isso percorrendo os imports internos.
"""

from __future__ import annotations

from pathlib import Path

from tree_sitter import Node

from damfe.adapters.driven.reconstruction.ast import AstReader, ImportTable
from damfe.adapters.driven.reconstruction.singlespa import http_clients
from damfe.adapters.driven.reconstruction.singlespa.context import ScanContext
from damfe.adapters.driven.reconstruction.singlespa.expressions import (
    ExpressionEvaluator,
)
from damfe.adapters.driven.reconstruction.singlespa.ownership import Ownership
from damfe.adapters.driven.reconstruction.singlespa.reachability import (
    Reachability,
)
from damfe.domain import ApiCall, MicroFrontend, SourceLocation


class ApiCallExtractor:

    def __init__(
        self,
        context: ScanContext,
        microfrontends: list[MicroFrontend],
    ):
        self.context = context

        self.ownership = Ownership(context.repository, microfrontends)

        self.evaluator = ExpressionEvaluator(context.routes)

        self.callers = self._callers(microfrontends)

    def extract(self) -> list[ApiCall]:

        found: list[ApiCall] = []

        for file_path in self.context.tree.source_files():

            try:
                root, source = self.context.reader.parse(file_path)
            except Exception:
                continue

            found.extend(self._from_file(file_path, root, source))

        return sorted(
            found,
            key=lambda item: (
                item.microfrontend,
                item.path,
                item.method,
                item.at.file,
                item.at.line,
            ),
        )

    def _callers(
        self,
        microfrontends: list[MicroFrontend],
    ) -> dict[Path, tuple[list[str], list[str]]]:
        """
        Arquivo -> (telas, fragmentos) que o alcançam.

        Invertido de propósito: a extração encontra a chamada e
        precisa perguntar quem chega até ali, não o contrário.
        """

        reachability = Reachability(self.context)

        screens: dict[Path, list[str]] = {}
        fragments: dict[Path, list[str]] = {}

        origins = [
            (screen.file, screen.component, screens)
            for microfrontend in microfrontends
            for screen in microfrontend.screens
        ] + [
            (fragment.file, fragment.name, fragments)
            for microfrontend in microfrontends
            for fragment in microfrontend.fragments
        ]

        for relative, name, target in origins:

            if not relative:
                continue

            origin = self.context.repository / relative

            if not origin.is_file():
                continue

            for reached in reachability.reachable_from(origin):
                target.setdefault(reached, []).append(name)

        return {
            path: (
                sorted(set(screens.get(path, []))),
                sorted(set(fragments.get(path, []))),
            )
            for path in set(screens) | set(fragments)
        }

    def _from_file(
        self,
        file_path: Path,
        root: Node,
        source: bytes,
    ) -> list[ApiCall]:

        bindings = self._bindings(root, source)

        owner = self.ownership.of_file(file_path)

        relative = self.context.relative(file_path)

        found: list[ApiCall] = []

        for node in AstReader.find_all(root, "call_expression"):

            call = (
                self._platform_call(node, source, bindings)
                or self._client_call(node, source, bindings)
            )

            if not call:
                continue

            method, path, match, client = call

            screens, fragments = self.callers.get(file_path, ([], []))

            found.append(
                ApiCall(
                    microfrontend=owner,
                    method=method,
                    path=path,
                    match=match,
                    client=client,
                    at=SourceLocation(
                        file=relative,
                        line=node.start_point.row + 1,
                        code=self._line(node, source),
                    ),
                    screens=screens,
                    fragments=fragments,
                )
            )

        return found

    # ------------------------------------------------------------------
    # Quem é cliente HTTP neste arquivo
    # ------------------------------------------------------------------

    def _bindings(self, root: Node, source: bytes) -> dict[str, str]:
        """
        Nomes locais que se comportam como cliente HTTP.

        Começa pelos imports das bibliotecas conhecidas e propaga
        para as instâncias criadas a partir delas — é o caso de
        `const api = axios.create({ baseURL })`, em que a chamada
        nunca acontece sobre o nome importado.
        """

        by_module = {client.module: client for client in http_clients.CLIENTS}

        bindings: dict[str, str] = {}

        for record in ImportTable.records(root, source):

            client = by_module.get(record.module)

            if client:
                bindings[record.local_name] = client.module

        # `new XMLHttpRequest()` também cria um cliente.
        for node in AstReader.find_all(root, "variable_declarator"):

            name_node = node.child_by_field_name("name")
            value_node = node.child_by_field_name("value")

            if not name_node or not value_node:
                continue

            if name_node.type != "identifier":
                continue

            name = AstReader.text(name_node, source)

            origin = self._origin(value_node, source, bindings, by_module)

            if origin:
                bindings[name] = origin

        return bindings

    @staticmethod
    def _origin(
        value: Node,
        source: bytes,
        bindings: dict[str, str],
        by_module: dict,
    ) -> str | None:

        text = AstReader.text(value, source).strip()

        if value.type == "new_expression":

            if http_clients.XHR_CONSTRUCTOR in text:
                return http_clients.XHR_CONSTRUCTOR

            return None

        # alias direto: `const client = axios`
        if value.type == "identifier" and text in bindings:
            return bindings[text]

        if value.type != "call_expression":
            return None

        function = value.child_by_field_name("function")

        if not function or function.type != "member_expression":
            return None

        receiver = function.child_by_field_name("object")
        method = function.child_by_field_name("property")

        if not receiver or not method:
            return None

        module = bindings.get(AstReader.text(receiver, source))

        if not module:
            return None

        client = by_module.get(module)

        if not client:
            return None

        return (
            module
            if AstReader.text(method, source) in client.factories
            else None
        )

    # ------------------------------------------------------------------
    # As chamadas
    # ------------------------------------------------------------------

    def _platform_call(
        self,
        node: Node,
        source: bytes,
        bindings: dict[str, str],
    ) -> tuple[str, str, str, str] | None:
        """`fetch(url, { method })` e `xhr.open(method, url)`."""

        function = node.child_by_field_name("function")

        if not function:
            return None

        text = AstReader.text(function, source)

        arguments = self._arguments(node)

        if text == http_clients.PLATFORM or text.endswith(
            f".{http_clients.PLATFORM}"
        ):

            if not arguments:
                return None

            value = self.evaluator.evaluate(arguments[0], source)

            if not value or not self._is_endpoint(value.url):
                return None

            method = self._method_option(arguments, source) or "GET"

            return method, value.url, value.match, "fetch"

        # xhr.open("GET", "/rota")
        if function.type == "member_expression":

            receiver = function.child_by_field_name("object")
            name = function.child_by_field_name("property")

            if not receiver or not name:
                return None

            if AstReader.text(name, source) != "open":
                return None

            if bindings.get(AstReader.text(receiver, source)) != (
                http_clients.XHR_CONSTRUCTOR
            ):
                return None

            if len(arguments) < 2:
                return None

            method = self.evaluator.evaluate(arguments[0], source)
            value = self.evaluator.evaluate(arguments[1], source)

            if not value or not self._is_endpoint(value.url):
                return None

            return (
                (method.url if method else "?").upper(),
                value.url,
                value.match,
                "xmlhttprequest",
            )

        return None

    def _client_call(
        self,
        node: Node,
        source: bytes,
        bindings: dict[str, str],
    ) -> tuple[str, str, str, str] | None:
        """`api.get(url)` e `axios({ url, method })`."""

        function = node.child_by_field_name("function")

        if not function:
            return None

        arguments = self._arguments(node)

        by_module = {item.module: item for item in http_clients.CLIENTS}

        if function.type == "member_expression":

            receiver = function.child_by_field_name("object")
            name = function.child_by_field_name("property")

            if not receiver or not name:
                return None

            module = bindings.get(AstReader.text(receiver, source))

            client = by_module.get(module or "")

            if not client:
                return None

            verb = AstReader.text(name, source)

            if verb not in client.methods:
                return None

            if not arguments:
                return None

            value = self.evaluator.evaluate(arguments[0], source)

            if not value or not self._is_endpoint(value.url):
                return None

            method = (
                self._method_option(arguments, source) or verb.upper()
                if verb == "request"
                else verb.upper()
            )

            return method, value.url, value.match, module

        # chamada direta na própria biblioteca: `axios({ url })`
        if function.type == "identifier":

            module = bindings.get(AstReader.text(function, source))

            client = by_module.get(module or "")

            if not client or not client.callable_directly or not arguments:
                return None

            value = self.evaluator.evaluate(arguments[0], source)

            if value and self._is_endpoint(value.url):
                method = self._method_option(arguments, source) or "GET"
                return method, value.url, value.match, module

            url = self._option(arguments[0], "url", source)

            if not url or not self._is_endpoint(url):
                return None

            method = self._option(arguments[0], "method", source)

            return (method or "GET").upper(), url, "exact", module

        return None

    # ------------------------------------------------------------------

    @staticmethod
    def _arguments(node: Node) -> list[Node]:

        arguments = node.child_by_field_name("arguments")

        if not arguments:
            return []

        return [
            child
            for child in arguments.named_children
            if child.type != "comment"
        ]

    def _method_option(
        self,
        arguments: list[Node],
        source: bytes,
    ) -> str | None:
        """O verbo declarado no objeto de opções, quando houver."""

        for argument in arguments[1:]:

            value = self._option(argument, "method", source)

            if value:
                return value.upper()

        return None

    def _option(
        self,
        node: Node,
        key: str,
        source: bytes,
    ) -> str | None:

        if node.type != "object":
            return None

        for pair in node.named_children:

            if pair.type != "pair":
                continue

            key_node = pair.child_by_field_name("key")
            value_node = pair.child_by_field_name("value")

            if not key_node or not value_node:
                continue

            if AstReader.strip_quotes(
                AstReader.text(key_node, source)
            ) != key:
                continue

            value = self.evaluator.evaluate(value_node, source)

            return value.url if value else None

        return None

    @staticmethod
    def _is_endpoint(value: str) -> bool:
        """
        Descarta o que claramente não é endereço de serviço.

        Caminho relativo de módulo e string vazia entram no
        avaliador pelos mesmos caminhos que uma URL; o filtro
        evita que virem chamada de API.
        """

        return bool(value) and (
            value.startswith("/") or value.startswith("http")
        )

    @staticmethod
    def _line(node: Node, source: bytes) -> str:

        return " ".join(AstReader.text(node, source).split())[:160]
