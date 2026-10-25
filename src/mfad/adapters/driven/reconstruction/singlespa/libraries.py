"""
Catálogos de bibliotecas conhecidas.

Mesma estratégia dos clientes HTTP: a biblioteca é reconhecida pelo
ESPECIFICADOR DO IMPORT, não pelo nome da variável nem por
heurística de texto. Isso é determinístico — se o módulo importado
é `react-redux`, o que vier dele é acesso a estado, chame-se a
variável como se chamar.

Os catálogos são o "nível 2" da extração. O nível 1 são as
primitivas da plataforma web, que não precisam de import nenhum e
valem em qualquer projeto.
"""

from __future__ import annotations

from dataclasses import dataclass


# ----------------------------------------------------------------------
# Nível 1 — primitivas da plataforma web
# ----------------------------------------------------------------------

#: `document.dispatchEvent(new CustomEvent(canal, ...))`
CUSTOM_EVENT = "CustomEvent"

DISPATCH = "dispatchEvent"

LISTEN = "addEventListener"

#: `fromEvent(window, "canal")` do rxjs: o mesmo ouvinte, escrito como
#: Observable. https://rxjs.dev/api/index/function/fromEvent
FROM_EVENT = "fromEvent"

#: Os alvos globais em que um evento atravessa micro frontends. Um
#: `fromEvent(botao, ...)` é evento de um elemento, não canal.
GLOBAL_TARGETS = frozenset({"window", "document", "globalThis", "self", "window.document"})

#: `new BroadcastChannel(canal)` e o `postMessage` sobre ela
BROADCAST_CHANNEL = "BroadcastChannel"

POST_MESSAGE = "postMessage"

#: `localStorage.setItem(chave, ...)` e `getItem(chave)`.
#:
#: Dois micro frontends que tocam a mesma chave estão acoplados pelo
#: formato do valor, e ninguém declarou esse contrato em lugar
#: nenhum. É estado global, não mensagem: a chave é a fatia, e quem
#: grava não manda nada a ninguém — deixa o dado lá para quem vier.
STORAGES = ("localStorage", "sessionStorage")

STORAGE_WRITE = ("setItem", "removeItem")

STORAGE_READ = ("getItem",)

#: `localStorage.clear()` apaga todas as chaves de uma vez: é escrita
#: em cada uma, sem nomear nenhuma. https://html.spec.whatwg.org/multipage/webstorage.html#dom-storage-clear
STORAGE_CLEAR = ("clear",)

#: A chave registrada para quem grava em todas.
ALL_KEYS = "*"

#: `subject.next(v)` e `subject.subscribe(fn)` sobre um Subject
#: IMPORTADO de um módulo compartilhado.
#:
#: É o canal canônico entre micro frontends Angular. O receptor
#: precisa vir de um import: `this.http.get(...).subscribe(...)` é
#: requisição HTTP, não canal, e casar pelo nome do método
#: transformaria metade de um projeto Angular em comunicação.
RX_PUBLISH = ("next",)

RX_SUBSCRIBE = ("subscribe",)

#: Módulos cujos exports são a própria biblioteca, não um canal.
RX_INTERNAL = ("rxjs", "rxjs/operators")

#: `alvo.postMessage({ type: "x" }, origem)` entre janelas.
#:
#: Diferente do `BroadcastChannel`, que leva o canal no construtor:
#: aqui o canal viaja DENTRO do payload, por convenção. Estes são os
#: nomes de campo que a convenção usa, em ordem de preferência.
MESSAGE_TYPE_FIELDS = ("type", "action", "event", "name")

#: O evento que entrega a mensagem do outro lado.
MESSAGE_EVENT = "message"


# ----------------------------------------------------------------------
# Nível 2 — barramentos de eventos conhecidos
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class EventBus:
    """Uma biblioteca de pub/sub e os nomes dos dois lados."""

    module: str
    publish: tuple[str, ...]
    subscribe: tuple[str, ...]

    #: fábrica que devolve a instância, ex.: `mitt()`
    factories: tuple[str, ...] = ()

    #: posição do canal nos argumentos
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
# Nível 2 — bibliotecas de estado global
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class StateLibrary:
    """
    Uma biblioteca de estado e como o código a consulta.

    `selectors` recebem uma função que percorre o estado — é dela
    que sai o caminho lido. `dispatchers` produzem a função que
    escreve; o nome despachado é o que se consegue registrar.
    `atoms` nomeiam o pedaço de estado diretamente.
    """

    module: str
    name: str
    selectors: tuple[str, ...] = ()
    dispatchers: tuple[str, ...] = ()
    atoms: tuple[str, ...] = ()


#: Quem cria um store Redux: `createStore` do redux e `configureStore`
#: do Redux Toolkit. https://redux.js.org/api/createstore e
#: https://redux-toolkit.js.org/api/configureStore
#:
#: Um micro frontend que cria o próprio store lê o PRÓPRIO estado. Duas
#: unidades com um store cada, ambas com a fatia `lookup`, não
#: compartilham nada — mesmo caminho, stores diferentes.
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
