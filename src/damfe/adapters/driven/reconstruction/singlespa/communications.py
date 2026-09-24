"""
Comunicação entre micro frontends, em três níveis.

1. PRIMITIVAS DA PLATAFORMA WEB — `CustomEvent` com
   `dispatchEvent`/`addEventListener`, e `BroadcastChannel`. São
   API do navegador, não de framework: valem em qualquer projeto,
   sem configuração.

2. BARRAMENTOS CONHECIDOS — mitt, eventemitter3, pubsub-js e
   afins, reconhecidos pelo especificador do import. Não é
   heurística: se o módulo importado é `mitt`, o que vier dele é
   barramento de eventos.

3. MECANISMO DECLARADO — o `.damfe/communication.yml`, para o
   wrapper próprio do projeto, que nenhum catálogo conhece.

Os três níveis produzem o mesmo artefato e são pareados juntos:
produtor e consumidor se encontram pelo NOME DO CANAL, que é o
contrato entre as duas pontas, não pela forma da chamada.

Sem declaração o resultado não é vazio — os dois primeiros níveis
continuam valendo.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Node

from damfe.adapters.driven.reconstruction.ast import AstReader, ImportTable
from damfe.adapters.driven.reconstruction.singlespa import libraries
from damfe.adapters.driven.reconstruction.singlespa.context import ScanContext
from damfe.adapters.driven.reconstruction.singlespa.expressions import (
    ExpressionEvaluator,
)
from damfe.adapters.driven.reconstruction.singlespa.ownership import Ownership
from damfe.domain import (
    MicroFrontend,
    ChannelOperation,
    Communication,
    CommunicationSpec,
    SourceLocation,
)


#: Eventos que o navegador dispara por conta própria. Um listener
#: neles é comportamento de página, não canal entre micro frontends.
NATIVE_EVENTS = frozenset(
    {
        "click", "change", "input", "submit", "focus", "blur",
        "keydown", "keyup", "keypress", "mousedown", "mouseup",
        "mousemove", "mouseover", "mouseout", "scroll", "resize",
        "load", "unload", "beforeunload", "DOMContentLoaded",
        "popstate", "hashchange", "storage", "message", "error",
        "touchstart", "touchend", "touchmove", "visibilitychange",
    }
)


@dataclass(frozen=True)
class Endpoint:
    """Uma ponta concreta: quem, em que canal, onde."""

    microfrontend: str
    channel: str
    file: str
    line: int
    code: str


class CommunicationExtractor:

    def __init__(
        self,
        context: ScanContext,
        microfrontends: list[MicroFrontend],
        spec: CommunicationSpec,
    ):
        self.context = context
        self.spec = spec

        self.ownership = Ownership(context.repository, microfrontends)

        self.known = {item.id for item in microfrontends}

        self.evaluator = ExpressionEvaluator(context.routes)

    def extract(self) -> list[Communication]:

        communications: list[Communication] = []

        # Nível 1 e 2: varrem o repositório uma vez, juntos.
        produced, consumed = self._generic()

        for mechanism in sorted(set(produced) | set(consumed)):

            communications.extend(
                self._pair(
                    mechanism,
                    produced.get(mechanism, []),
                    consumed.get(mechanism, []),
                )
            )

        # Nível 3: o que o usuário declarou.
        for mechanism in self.spec.mechanisms:

            communications.extend(
                self._pair(
                    mechanism.name,
                    self._endpoints(mechanism.produce),
                    self._endpoints(mechanism.consume),
                )
            )

        return sorted(
            communications,
            key=lambda item: (item.source, item.target, item.channel),
        )

    # ------------------------------------------------------------------
    # Níveis 1 e 2 — sem configuração
    # ------------------------------------------------------------------

    def _generic(
        self,
    ) -> tuple[dict[str, list[Endpoint]], dict[str, list[Endpoint]]]:

        produced: dict[str, list[Endpoint]] = {}
        consumed: dict[str, list[Endpoint]] = {}

        for file_path in self.context.tree.source_files():

            try:
                root, source = self.context.reader.parse(file_path)
            except Exception:
                continue

            owner = self.ownership.of_file(file_path)

            # Uso dentro de pacote compartilhado não é comunicação
            # entre micro frontends — não há de quem para quem.
            if owner not in self.known:
                continue

            buses = self._buses(root, source)

            for node in AstReader.find_all(root, "call_expression"):

                found = self._platform(node, source) or self._bus(
                    node, source, buses
                )

                if not found:
                    continue

                mechanism, channel, side = found

                endpoint = Endpoint(
                    microfrontend=owner,
                    channel=channel,
                    file=self.context.relative(file_path),
                    line=node.start_point.row + 1,
                    code=" ".join(
                        AstReader.text(node, source).split()
                    )[:160],
                )

                target = produced if side == "produce" else consumed

                target.setdefault(mechanism, []).append(endpoint)

        return produced, consumed

    def _platform(
        self,
        node: Node,
        source: bytes,
    ) -> tuple[str, str, str] | None:
        """`dispatchEvent(new CustomEvent(canal))` e `addEventListener`."""

        function = node.child_by_field_name("function")

        if not function:
            return None

        name = AstReader.text(function, source).rpartition(".")[2]

        arguments = self._call_arguments(node)

        if not arguments:
            return None

        if name == libraries.DISPATCH:

            channel = self._event_channel(arguments[0], source)

            return ("CustomEvent", channel, "produce") if channel else None

        if name == libraries.LISTEN:

            channel = self._value(arguments[0], source)

            # Eventos do próprio navegador não são comunicação
            # entre micro frontends.
            if not channel or channel in NATIVE_EVENTS:
                return None

            return "CustomEvent", channel, "consume"

        if name == libraries.POST_MESSAGE:

            channel = self._value(arguments[0], source)

            return (
                (libraries.BROADCAST_CHANNEL, channel, "produce")
                if channel
                else None
            )

        return None

    def _event_channel(self, node: Node, source: bytes) -> str | None:
        """O canal de `new CustomEvent(canal, ...)`."""

        if node.type != "new_expression":
            return None

        constructor = node.child_by_field_name("constructor")

        if not constructor:
            return None

        if AstReader.text(constructor, source) != libraries.CUSTOM_EVENT:
            return None

        arguments = self._call_arguments(node)

        return self._value(arguments[0], source) if arguments else None

    @staticmethod
    def _buses(root: Node, source: bytes) -> dict[str, tuple]:
        """Nome local -> (barramento, papel), pelos imports."""

        by_module = {bus.module: bus for bus in libraries.EVENT_BUSES}

        bindings: dict[str, tuple] = {}

        for record in ImportTable.records(root, source):

            bus = by_module.get(record.module)

            if bus:
                bindings[record.local_name] = bus

        # Instâncias criadas a partir deles: `const bus = mitt()`
        for node in AstReader.find_all(root, "variable_declarator"):

            name_node = node.child_by_field_name("name")
            value_node = node.child_by_field_name("value")

            if not name_node or not value_node:
                continue

            if value_node.type != "call_expression":
                continue

            function = value_node.child_by_field_name("function")

            if not function:
                continue

            bus = bindings.get(AstReader.text(function, source))

            if bus:
                bindings[AstReader.text(name_node, source)] = bus

        return bindings

    def _bus(
        self,
        node: Node,
        source: bytes,
        buses: dict[str, tuple],
    ) -> tuple[str, str, str] | None:
        """`bus.emit(canal, ...)` e `bus.on(canal, ...)`."""

        function = node.child_by_field_name("function")

        if not function or function.type != "member_expression":
            return None

        receiver = function.child_by_field_name("object")
        method = function.child_by_field_name("property")

        if not receiver or not method:
            return None

        bus = buses.get(AstReader.text(receiver, source))

        if not bus:
            return None

        verb = AstReader.text(method, source)

        if verb in bus.publish:
            side = "produce"
        elif verb in bus.subscribe:
            side = "consume"
        else:
            return None

        arguments = self._call_arguments(node)

        index = bus.channel_argument

        if index >= len(arguments):
            return None

        channel = self._value(arguments[index], source)

        return (bus.module, channel, side) if channel else None

    def _value(self, node: Node, source: bytes) -> str | None:
        """Resolve o canal: literal, constante, ou o texto da expressão."""

        if node.type == "string":
            return AstReader.strip_quotes(AstReader.text(node, source))

        value = self.evaluator.evaluate(node, source)

        if value:
            return value.url

        if node.type in {"identifier", "member_expression", "subscript_expression"}:
            return AstReader.text(node, source)

        return None

    @staticmethod
    def _call_arguments(node: Node) -> list[Node]:

        arguments = node.child_by_field_name("arguments")

        if not arguments:
            return []

        return [
            child
            for child in arguments.named_children
            if child.type != "comment"
        ]

    # ------------------------------------------------------------------
    # Nível 3 — mecanismo declarado
    # ------------------------------------------------------------------

    def _endpoints(
        self,
        operation: ChannelOperation,
    ) -> list[Endpoint]:

        found: list[Endpoint] = []

        for file_path in self.context.tree.source_files():

            try:
                root, source = self.context.reader.parse(file_path)
            except Exception:
                continue

            names = self._local_names(root, source, operation)

            if not names:
                continue

            found.extend(
                self._calls(file_path, root, source, names, operation)
            )

        return found

    @staticmethod
    def _local_names(
        root: Node,
        source: bytes,
        operation: ChannelOperation,
    ) -> set[str]:
        """
        Os nomes pelos quais a função declarada é conhecida NESTE
        arquivo. Resolver pelo import, e não pelo nome da chamada,
        é o que faz um alias (`import { x as y }`) ser reconhecido.
        """

        return {
            record.local_name
            for record in ImportTable.records(root, source)
            if record.module == operation.module
            and record.imported_name == operation.export
        }

    def _calls(
        self,
        file_path: Path,
        root: Node,
        source: bytes,
        names: set[str],
        operation: ChannelOperation,
    ) -> list[Endpoint]:

        microfrontend = self.ownership.of_file(file_path)

        relative = self.context.relative(file_path)

        found: list[Endpoint] = []

        for node in AstReader.find_all(root, "call_expression"):

            function = node.child_by_field_name("function")

            if not function:
                continue

            if AstReader.text(function, source) not in names:
                continue

            channel = self._channel(node, source, operation)

            if not channel:
                continue

            found.append(
                Endpoint(
                    microfrontend=microfrontend,
                    channel=channel,
                    file=relative,
                    line=node.start_point.row + 1,
                    code=" ".join(
                        AstReader.text(node, source).split()
                    )[:160],
                )
            )

        return found

    def _channel(
        self,
        node: Node,
        source: bytes,
        operation: ChannelOperation,
    ) -> str | None:

        arguments = node.child_by_field_name("arguments")

        if not arguments:
            return None

        parts = [
            child
            for child in arguments.named_children
            if child.type != "comment"
        ]

        index = operation.channel_argument

        if index >= len(parts):
            return None

        argument = parts[index]

        if argument.type == "string":
            return AstReader.strip_quotes(
                AstReader.text(argument, source)
            )

        # Canal vindo de constante, como `eventTopics.CART_UPDATED`.
        value = self.evaluator.evaluate(argument, source)

        if value:
            return value.url

        # Sem resolver o valor, o identificador ainda serve de canal:
        # as duas pontas costumam referenciar a mesma constante.
        if argument.type in {"identifier", "member_expression"}:
            return AstReader.text(argument, source)

        return None

    # ------------------------------------------------------------------
    # Parear pelas duas pontas
    # ------------------------------------------------------------------

    @staticmethod
    def _pair(
        mechanism: str,
        produced: list[Endpoint],
        consumed: list[Endpoint],
    ) -> list[Communication]:

        by_channel: dict[str, dict[str, list[Endpoint]]] = defaultdict(
            lambda: {"produce": [], "consume": []}
        )

        for endpoint in produced:
            by_channel[endpoint.channel]["produce"].append(endpoint)

        for endpoint in consumed:
            by_channel[endpoint.channel]["consume"].append(endpoint)

        communications: list[Communication] = []

        for channel, sides in by_channel.items():

            producers = {item.microfrontend for item in sides["produce"]}
            consumers = {item.microfrontend for item in sides["consume"]}

            for producer in sorted(producers):

                for consumer in sorted(consumers):

                    if producer == consumer:
                        continue

                    communications.append(
                        Communication(
                            source=producer,
                            target=consumer,
                            mechanism=mechanism,
                            channel=channel,
                            produced_at=[
                                SourceLocation(
                                    file=item.file,
                                    line=item.line,
                                    code=item.code,
                                )
                                for item in sides["produce"]
                                if item.microfrontend == producer
                            ],
                            consumed_at=[
                                SourceLocation(
                                    file=item.file,
                                    line=item.line,
                                    code=item.code,
                                )
                                for item in sides["consume"]
                                if item.microfrontend == consumer
                            ],
                        )
                    )

        return communications
