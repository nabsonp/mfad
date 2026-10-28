"""
Catalogs of known libraries.

Same strategy as the HTTP clients: the library is recognized by the
IMPORT SPECIFIER, not by the variable name nor by a text heuristic.
This is deterministic — if the imported module is `react-redux`,
whatever comes from it is state access, whatever the variable is
called.

The catalogs are "level 2" of the extraction. Level 1 is the web
platform primitives, which need no import at all and apply to any
project.
"""

from __future__ import annotations

from dataclasses import dataclass


# ----------------------------------------------------------------------
# Level 1 — web platform primitives
# ----------------------------------------------------------------------

#: `document.dispatchEvent(new CustomEvent(canal, ...))`
CUSTOM_EVENT = "CustomEvent"

DISPATCH = "dispatchEvent"

LISTEN = "addEventListener"

#: rxjs's `fromEvent(window, "canal")`: the same listener, written as
#: an Observable. https://rxjs.dev/api/index/function/fromEvent
FROM_EVENT = "fromEvent"

#: The global targets on which an event crosses micro frontends. A
#: `fromEvent(botao, ...)` is an element's event, not a channel.
GLOBAL_TARGETS = frozenset({"window", "document", "globalThis", "self", "window.document"})

#: `new BroadcastChannel(canal)` and the `postMessage` on it
BROADCAST_CHANNEL = "BroadcastChannel"

POST_MESSAGE = "postMessage"

#: `localStorage.setItem(chave, ...)` and `getItem(chave)`.
#:
#: Two micro frontends that touch the same key are coupled by the
#: value's format, and nobody declared that contract anywhere. It is
#: global state, not a message: the key is the slice, and the writer
#: sends nothing to anyone — it leaves the data there for whoever comes.
STORAGES = ("localStorage", "sessionStorage")

STORAGE_WRITE = ("setItem", "removeItem")

STORAGE_READ = ("getItem",)

#: `localStorage.clear()` erases every key at once: it is a write to
#: each one, without naming any. https://html.spec.whatwg.org/multipage/webstorage.html#dom-storage-clear
STORAGE_CLEAR = ("clear",)

#: The key recorded for whoever writes to all of them.
ALL_KEYS = "*"

#: `subject.next(v)` and `subject.subscribe(fn)` on a Subject
#: IMPORTED from a shared module.
#:
#: It is the canonical channel between Angular micro frontends. The
#: receiver must come from an import: `this.http.get(...).subscribe(...)`
#: is an HTTP request, not a channel, and matching by method name would
#: turn half of an Angular project into communication.
RX_PUBLISH = ("next",)

RX_SUBSCRIBE = ("subscribe",)

#: Modules whose exports are the library itself, not a channel.
RX_INTERNAL = ("rxjs", "rxjs/operators")

#: `alvo.postMessage({ type: "x" }, origem)` between windows.
#:
#: Unlike `BroadcastChannel`, which carries the channel in the
#: constructor: here the channel travels INSIDE the payload, by
#: convention. These are the field names the convention uses, in order
#: of preference.
MESSAGE_TYPE_FIELDS = ("type", "action", "event", "name")

#: The event that delivers the message on the other side.
MESSAGE_EVENT = "message"


# ----------------------------------------------------------------------
# Level 2 — known event buses
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class EventBus:
    """A pub/sub library and the names of its two sides."""

    module: str
    publish: tuple[str, ...]
    subscribe: tuple[str, ...]

    #: factory that returns the instance, e.g. `mitt()`
    factories: tuple[str, ...] = ()

    #: position of the channel among the arguments
    channel_argument: int = 0


EVENT_BUSES = (
    EventBus(
        module="mitt",
        publish=("emit",),
        subscribe=("on",),
        factories=("mitt", "default"),
    ),
    EventBus(
        module="eventemitter3",
        publish=("emit",),
        subscribe=("on", "once", "addListener"),
        factories=("default",),
    ),
    EventBus(
        module="tiny-emitter",
        publish=("emit",),
        subscribe=("on", "once"),
        factories=("default",),
    ),
    EventBus(
        module="pubsub-js",
        publish=("publish", "publishSync"),
        subscribe=("subscribe",),
        factories=("default",),
    ),
)


# ----------------------------------------------------------------------
# Level 2 — global state libraries
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class StateLibrary:
    """
    A state library and how the code queries it.

    `selectors` receive a function that walks the state — the read path
    comes from it. `dispatchers` produce the function that writes; the
    dispatched name is what can be recorded. `atoms` name the piece of
    state directly.
    """

    module: str
    name: str
    selectors: tuple[str, ...] = ()
    dispatchers: tuple[str, ...] = ()
    atoms: tuple[str, ...] = ()


#: Who creates a Redux store: redux's `createStore` and Redux Toolkit's
#: `configureStore`. https://redux.js.org/api/createstore and
#: https://redux-toolkit.js.org/api/configureStore
#:
#: A micro frontend that creates its own store reads its OWN state. Two
#: units with one store each, both with the `lookup` slice, share
#: nothing — same path, different stores.
REDUX_STORE_FACTORIES = (
    ("redux", "createStore"),
    ("redux", "legacy_createStore"),
    ("@reduxjs/toolkit", "configureStore"),
    ("@reduxjs/toolkit", "createStore"),
)

STATE_LIBRARIES = (
    StateLibrary(
        module="react-redux",
        name="redux",
        selectors=("useSelector",),
        dispatchers=("useDispatch",),
    ),
    StateLibrary(
        module="zustand",
        name="zustand",
        selectors=("useStore", "create"),
    ),
    StateLibrary(
        module="jotai",
        name="jotai",
        atoms=("useAtom", "useAtomValue", "useSetAtom"),
    ),
    StateLibrary(
        module="recoil",
        name="recoil",
        atoms=("useRecoilValue", "useRecoilState", "useSetRecoilState"),
    ),
    StateLibrary(
        module="mobx-react-lite",
        name="mobx",
        selectors=("observer",),
    ),
    StateLibrary(
        module="pinia",
        name="pinia",
        selectors=("storeToRefs",),
    ),
)
