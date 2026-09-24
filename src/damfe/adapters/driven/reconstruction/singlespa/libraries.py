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

#: `new BroadcastChannel(canal)` e o `postMessage` sobre ela
BROADCAST_CHANNEL = "BroadcastChannel"

POST_MESSAGE = "postMessage"


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
