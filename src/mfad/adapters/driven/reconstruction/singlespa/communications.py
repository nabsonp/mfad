"""
Communication between micro frontends, at three levels.

1. WEB PLATFORM PRIMITIVES — `CustomEvent` with
   `dispatchEvent`/`addEventListener`, and `BroadcastChannel`. They
   are browser API, not framework API: they apply to any project,
   with no configuration.

2. KNOWN BUSES — mitt, eventemitter3, pubsub-js and the like,
   recognized by the import specifier. This is not a heuristic: if
   the imported module is `mitt`, whatever comes from it is an event
   bus.

3. DECLARED MECHANISM — `.mfad/communication.yml`, for the project's
   own wrapper, which no catalog knows about.

The three levels produce the same artifact and are paired together:
producer and consumer meet by the CHANNEL NAME, which is the contract
between the two ends, not by the shape of the call.

Without a declaration the result is not empty — the first two levels
still apply.
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


#: Events the browser fires on its own. A listener on them is page
#: behavior, not a channel between micro frontends.
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
    """A concrete end: who, on which channel, where."""

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

        # Levels 1 and 2: scan the repository once, together.
        produced, consumed = self._generic()

        for mechanism in sorted(set(produced) | set(consumed)):

            communications.extend(
                self._pair(
                    mechanism,
                    produced.get(mechanism, []),
                    consumed.get(mechanism, []),
                )
            )

        # Declared by the technology itself: the orchestrator states, in
        # the registration, what it injects into each application.
        communications.extend(self._custom_props())

        # Level 3: what the user declared.
        for mechanism in self.spec.mechanisms:

            communications.extend(
                self._pair(
                    mechanism.name,
                    self._endpoints(mechanism.produce),
                    self._endpoints(mechanism.consume),
                )
            )

        # Where each end happens. Done last, and only once, because it
        # applies equally to the three levels: the mechanism does not
        # change the question of which screen reaches the call's file.
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
    # customProps — declared by the registration
    # ------------------------------------------------------------------

    def _custom_props(self) -> list[Communication]:
        """
        `registerApplication({ name, customProps: { … } })`.

        It is the channel recommended by single-spa and the only one
        that does not need pairing: the registration names BOTH ends at
        once. The injector is the orchestrator, the receiver is the
        application named there, and each key is a channel.

        That is why the edge is directed. The others arise from two
        ends that meet by a channel name and may be symmetric; this one
        has its source and target written in the declaration.
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
        """The orchestrator that mounts this application."""

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
    # Levels 1 and 2 — no configuration
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

            # Usage inside a shared package is not communication
            # between micro frontends — there is no from-whom-to-whom.
            if owner not in self.known:
                continue

            buses = self._buses(root, source)

            #: local name -> source module, to recognize the shared
            #: Subject by its import and not by its name.
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

                # An end in a function nothing calls does not communicate.
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
        """`dispatchEvent(new CustomEvent(canal))` and `addEventListener`."""

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

            # The browser's own events are not communication between
            # micro frontends.
            if not channel or channel in NATIVE_EVENTS:
                return None

            return "CustomEvent", channel, "consume"

        if name == libraries.POST_MESSAGE:

            # Two APIs with the same name. `BroadcastChannel` receives
            # only the payload, because the channel is in the
            # constructor; cross-window `postMessage` receives payload
            # and origin, and then the channel is inside the payload.
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
        The field that acts as the channel in `postMessage({…}, origem)`.

        Convention, not API: the platform defines no channel name here,
        and the ecosystem settled on a `type` field in the payload. A
        payload that is not an object literal, or that has none of the
        known fields, produces no channel — better not to record one
        than to invent it.
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
        The channels an `addEventListener("message", handler)` handles.

        There is a single listener for all channels, so what tells one
        from another are the comparisons inside the handler —
        `event.data.type === "cart:updated"`. We look for literals
        compared to a field of the convention, and only inside the
        handler: outside it, any string would become a channel.
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
        """Literals compared to a type field inside the handler."""

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
        The channel of `new CustomEvent(canal, ...)`.

        The event is usually created first and dispatched later:

            const evento = new CustomEvent("carrinho", { detail });
            window.dispatchEvent(evento);

        and then the channel is in the variable declaration, not in the
        call. The name is followed to the nearest declaration in the
        same scope. `Event` is included too: `new Event("x")` also
        carries the type.
        """

        node = unwrap(node)

        if node.type == "identifier":
            node = declared_value(node, source)

            if node is None:
                return None

        # `new CustomEvent("x") as EventoTipado`: the type annotation
        # does not change the event.
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
        """Local name -> (bus, role), from the imports."""

        by_module = {bus.module: bus for bus in libraries.EVENT_BUSES}

        bindings: dict[str, tuple] = {}

        for record in ImportTable.records(root, source):

            bus = by_module.get(record.module)

            if bus:
                bindings[record.local_name] = bus

        # Instances created from them: `const bus = mitt()`
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
        """`bus.emit(canal, ...)` and `bus.on(canal, ...)`."""

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
        `cart$.next(v)` and `cart$.subscribe(fn)` on an imported symbol.

        The channel is the symbol's identity — module plus name —, not
        a string. Two units that import the same `cart$` from the same
        module are at the two ends of the same channel, and that is
        what pairs them.

        The root of the expression must be in the import table. Without
        this requirement, `this.http.get(url).subscribe(...)` would
        become communication and a whole Angular project would become
        noise.
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
        """Resolves the channel: literal, constant, or the expression's text."""

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
    # Level 3 — declared mechanism
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
        The names by which the declared function is known in THIS
        file. Resolving through the import, and not by the call's name,
        is what lets an alias (`import { x as y }`) be recognized.
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

        # Channel coming from a constant, such as `eventTopics.CART_UPDATED`.
        value = self.evaluator.evaluate(argument, source)

        if value and value.match == EXACT and not value.based:
            return value.url

        # Without resolving the value, the identifier still serves as
        # the channel: both ends usually reference the same constant.
        if argument.type in {"identifier", "member_expression"}:
            return AstReader.text(argument, source)

        return None

    # ------------------------------------------------------------------
    # Pair by the two ends
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
