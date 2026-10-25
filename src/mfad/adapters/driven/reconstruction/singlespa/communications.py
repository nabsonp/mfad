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

3. MECANISMO DECLARADO — o `.mfad/communication.yml`, para o
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

from mfad.adapters.driven.reconstruction.ast import AstReader, ImportTable
from mfad.adapters.driven.reconstruction.ast.symbols import (
    ModuleSymbols,
    declared_value,
    unwrap,
)
from mfad.adapters.driven.reconstruction.singlespa import libraries
from mfad.adapters.driven.reconstruction.singlespa.context import ScanContext
from mfad.adapters.driven.reconstruction.singlespa.expressions import (
    EXACT,
    ExpressionEvaluator,
)
from mfad.adapters.driven.reconstruction.singlespa.liveness import Liveness
from mfad.adapters.driven.reconstruction.singlespa.ownership import Ownership
from mfad.adapters.driven.reconstruction.singlespa.reachability import (
    placement_of,
    placements,
)
from mfad.domain import (
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

        self.microfrontends = microfrontends

        self.ownership = Ownership(context.repository, microfrontends)

        self.known = {item.id for item in microfrontends}

        self.evaluator = ExpressionEvaluator(context.routes)

        self.liveness = Liveness(context)

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

        # Declarado pela própria tecnologia: o orquestrador diz, no
        # registro, o que injeta em cada aplicação.
        communications.extend(self._custom_props())

        # Nível 3: o que o usuário declarou.
        for mechanism in self.spec.mechanisms:

            communications.extend(
                self._pair(
                    mechanism.name,
                    self._endpoints(mechanism.produce),
                    self._endpoints(mechanism.consume),
                )
            )

        # Onde cada ponta acontece. Feito por último, e uma vez só,
        # porque vale para os três níveis igualmente: o mecanismo não
        # muda a pergunta de qual tela alcança o arquivo da chamada.
        found = placements(self.context, self.microfrontends)

        for item in communications:

            item.produced_on = placement_of(
                found, [location.file for location in item.produced_at]
            )
            item.consumed_on = placement_of(
                found, [location.file for location in item.consumed_at]
            )

        return sorted(
            communications,
            key=lambda item: (item.source, item.target, item.channel),
        )

    # ------------------------------------------------------------------
    # customProps — declarado pelo registro
    # ------------------------------------------------------------------

    def _custom_props(self) -> list[Communication]:
        """
        `registerApplication({ name, customProps: { … } })`.

        É o canal recomendado pelo single-spa e o único que não
        precisa ser pareado: o registro nomeia as DUAS pontas de uma
        vez. Quem injeta é o orquestrador, quem recebe é a aplicação
        nomeada ali, e cada chave é um canal.

        Por isso a aresta é dirigida. As demais nascem de duas pontas
        que se encontram por um nome de canal e podem ser simétricas;
        esta tem origem e destino escritos na declaração.
        """

        orchestrators = [
            item.id
            for item in self.microfrontends
            if item.role == "shell"
        ]

        if not orchestrators:
            return []

        found: list[Communication] = []

        for item in self.microfrontends:

            keys = item.metadata.get("custom_props") or {}

            if not keys:
                continue

            source_id = self._injector(item.id, orchestrators)

            if not source_id or source_id == item.id:
                continue

            location = SourceLocation(
                file=self._registration_file(item.id),
                line=0,
                code=f"customProps: {{ {', '.join(sorted(keys))} }}",
            )

            for key in sorted(keys):

                found.append(
                    Communication(
                        source=source_id,
                        target=item.id,
                        mechanism="customProps",
                        channel=key,
                        produced_at=[location],
                        consumed_at=[],
                        directed=True,
                    )
                )

        return found

    def _injector(self, target: str, orchestrators: list[str]) -> str | None:
        """O orquestrador que monta esta aplicação."""

        for item in self.microfrontends:

            if item.id in orchestrators and target in item.mounts:
                return item.id

        return orchestrators[0] if len(orchestrators) == 1 else None

    def _registration_file(self, target: str) -> str:

        for registration in self.context.registrations:

            if registration.name == target:
                return self.context.relative(registration.declared_in)

        return ""

    # ------------------------------------------------------------------
    # Níveis 1 e 2 — sem configuração
    # ------------------------------------------------------------------

    def _generic(
        self,
    ) -> tuple[dict[str, list[Endpoint]], dict[str, list[Endpoint]]]:

        produced: dict[str, list[Endpoint]] = {}
        consumed: dict[str, list[Endpoint]] = {}

        for file_path in self.context.tree.source_files():

            symbols = self.context.symbols().of(file_path)

            if symbols is None:
                continue

            root, source = symbols.root, symbols.source

            owner = self.ownership.of_file(file_path)

            # Uso dentro de pacote compartilhado não é comunicação
            # entre micro frontends — não há de quem para quem.
            if owner not in self.known:
                continue

            buses = self._buses(root, source)

            #: nome local -> módulo de origem, para reconhecer o
            #: Subject compartilhado pelo import e não pelo nome.
            imported = {
                record.local_name: record.module
                for record in ImportTable.records(root, source)
            }

            for node in AstReader.find_all(root, "call_expression"):

                found = (
                    self._platform(node, source)
                    or self._bus(node, source, buses)
                    or self._subject(node, source, imported)
                )

                if not found:
                    continue

                # Ponta em função que nada chama não comunica.
                if not self.liveness.is_live(node, symbols):
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

            for channel, call in self._message_listeners(root, source):

                if not self.liveness.is_live(call, symbols):
                    continue

                consumed.setdefault("postMessage", []).append(
                    Endpoint(
                        microfrontend=owner,
                        channel=channel,
                        file=self.context.relative(file_path),
                        line=call.start_point.row + 1,
                        code=" ".join(
                            AstReader.text(call, source).split()
                        )[:160],
                    )
                )

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

            if not channel or channel in NATIVE_EVENTS:
                return None

            return "CustomEvent", channel, "produce"

        if name == libraries.FROM_EVENT and len(arguments) >= 2:

            if AstReader.text(arguments[0], source) not in libraries.GLOBAL_TARGETS:
                return None

            channel = self._value(arguments[1], source)

            if not channel or channel in NATIVE_EVENTS:
                return None

            return "CustomEvent", channel, "consume"

        if name == libraries.LISTEN:

            channel = self._value(arguments[0], source)

            # Eventos do próprio navegador não são comunicação
            # entre micro frontends.
            if not channel or channel in NATIVE_EVENTS:
                return None

            return "CustomEvent", channel, "consume"

        if name == libraries.POST_MESSAGE:

            # Duas APIs com o mesmo nome. `BroadcastChannel` recebe
            # só o payload, porque o canal está no construtor; o
            # `postMessage` entre janelas recebe payload e origem, e
            # aí o canal está dentro do payload.
            if len(arguments) >= 2:

                channel = self._message_type(arguments[0], source)

                return (
                    ("postMessage", channel, "produce") if channel else None
                )

            channel = self._value(arguments[0], source)

            return (
                (libraries.BROADCAST_CHANNEL, channel, "produce")
                if channel
                else None
            )

        return None

    def _message_type(self, node: Node, source: bytes) -> str | None:
        """
        O campo que faz as vezes de canal em `postMessage({…}, origem)`.

        Convenção, não API: a plataforma não define nome de canal
        aqui, e o ecossistema resolveu isso com um campo `type` no
        payload. Payload que não seja literal de objeto, ou sem
        nenhum dos campos conhecidos, não produz canal — é melhor não
        registrar do que inventar um.
        """

        if node.type != "object":
            return None

        fields = {}

        for pair in node.named_children:

            if pair.type != "pair":
                continue

            key = pair.child_by_field_name("key")
            value = pair.child_by_field_name("value")

            if not key or not value or value.type != "string":
                continue

            fields[AstReader.strip_quotes(AstReader.text(key, source))] = (
                AstReader.strip_quotes(AstReader.text(value, source))
            )

        for candidate in libraries.MESSAGE_TYPE_FIELDS:

            if candidate in fields:
                return fields[candidate]

        return None

    def _message_listeners(
        self,
        root: Node,
        source: bytes,
    ) -> list[tuple[str, Node]]:
        """
        Os canais que um `addEventListener("message", handler)` trata.

        O ouvinte é um só para todos os canais, então o que distingue
        um do outro são as comparações dentro do tratador —
        `event.data.type === "cart:updated"`. Procuram-se os literais
        comparados a um campo da convenção, e só dentro do tratador:
        fora dele, qualquer string viraria canal.
        """

        found: list[tuple[str, Node]] = []

        for call in AstReader.find_all(root, "call_expression"):

            function = call.child_by_field_name("function")

            if not function:
                continue

            if AstReader.text(function, source).rpartition(".")[2] != (
                libraries.LISTEN
            ):
                continue

            arguments = self._call_arguments(call)

            if len(arguments) < 2:
                continue

            if self._value(arguments[0], source) != libraries.MESSAGE_EVENT:
                continue

            for channel in self._compared_literals(arguments[1], source):
                found.append((channel, call))

        return found

    @staticmethod
    def _compared_literals(handler: Node, source: bytes) -> list[str]:
        """Literais comparados a um campo de tipo dentro do tratador."""

        found = []

        for node in AstReader.find_all(handler, "binary_expression"):

            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")

            if not left or not right:
                continue

            for a, b in ((left, right), (right, left)):

                if b.type != "string":
                    continue

                field = AstReader.text(a, source).rpartition(".")[2]

                if field in libraries.MESSAGE_TYPE_FIELDS:
                    found.append(
                        AstReader.strip_quotes(AstReader.text(b, source))
                    )

        return found

    def _event_channel(self, node: Node, source: bytes) -> str | None:
        """
        O canal de `new CustomEvent(canal, ...)`.

        O evento costuma ser criado antes e disparado depois:

            const evento = new CustomEvent("carrinho", { detail });
            window.dispatchEvent(evento);

        e então o canal está na declaração da variável, não na chamada.
        Segue-se o nome até a declaração mais próxima no mesmo escopo.
        `Event` entra junto: `new Event("x")` também carrega o tipo.
        """

        node = unwrap(node)

        if node.type == "identifier":
            node = declared_value(node, source)

            if node is None:
                return None

        # `new CustomEvent("x") as EventoTipado`: a anotação de tipo
        # não muda o evento.
        node = unwrap(node)

        if node.type != "new_expression":
            return None

        constructor = node.child_by_field_name("constructor")

        if not constructor:
            return None

        if AstReader.text(constructor, source) not in (libraries.CUSTOM_EVENT, "Event"):
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

    def _subject(
        self,
        node: Node,
        source: bytes,
        imported: dict[str, str],
    ) -> tuple[str, str, str] | None:
        """
        `cart$.next(v)` e `cart$.subscribe(fn)` sobre símbolo importado.

        O canal é a identidade do símbolo — módulo mais nome —, não
        uma string. Duas unidades que importam o mesmo `cart$` do
        mesmo módulo estão nas duas pontas do mesmo canal, e é isso
        que as pareia.

        A raiz da expressão precisa estar na tabela de imports. Sem
        essa exigência, `this.http.get(url).subscribe(...)` viraria
        comunicação e um projeto Angular inteiro viraria ruído.
        """

        function = node.child_by_field_name("function")

        if not function or function.type != "member_expression":
            return None

        method = function.child_by_field_name("property")

        if not method:
            return None

        verb = AstReader.text(method, source)

        if verb in libraries.RX_PUBLISH:
            side = "produce"
        elif verb in libraries.RX_SUBSCRIBE:
            side = "consume"
        else:
            return None

        receiver = function.child_by_field_name("object")

        if not receiver or receiver.type not in {
            "identifier",
            "member_expression",
        }:
            return None

        path = AstReader.text(receiver, source)

        root_name = path.split(".")[0]

        module = imported.get(root_name)

        if not module or module in libraries.RX_INTERNAL:
            return None

        return "rxjs-subject", f"{module}#{path}", side

    def _value(self, node: Node, source: bytes) -> str | None:
        """Resolve o canal: literal, constante, ou o texto da expressão."""

        if node.type == "string":
            return AstReader.strip_quotes(AstReader.text(node, source))

        value = self.evaluator.evaluate(node, source)

        if value and value.match == EXACT and not value.based:
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

            symbols = self.context.symbols().of(file_path)

            if symbols is None:
                continue

            names = self._local_names(symbols.root, symbols.source, operation)

            if not names:
                continue

            found.extend(
                self._calls(file_path, symbols, names, operation)
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
        symbols: ModuleSymbols,
        names: set[str],
        operation: ChannelOperation,
    ) -> list[Endpoint]:

        root, source = symbols.root, symbols.source

        microfrontend = self.ownership.of_file(file_path)

        if microfrontend not in self.known:
            return []

        relative = self.context.relative(file_path)

        found: list[Endpoint] = []

        for node in AstReader.find_all(root, "call_expression"):

            function = node.child_by_field_name("function")

            if not function:
                continue

            if AstReader.text(function, source) not in names:
                continue

            channel = self._channel(node, source, operation)

            if not channel or not self.liveness.is_live(node, symbols):
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

        if value and value.match == EXACT and not value.based:
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
