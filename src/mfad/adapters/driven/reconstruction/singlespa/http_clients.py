"""
Como o código faz chamadas HTTP.

Três camadas, da mais genérica para a mais específica:

1. `fetch` e `XMLHttpRequest` são API da plataforma web. Existem
   em qualquer projeto, com qualquer framework — é o equivalente
   do `activeWhen` para roteamento: contrato duro, não convenção.

2. Bibliotecas conhecidas são identificadas pelo ESPECIFICADOR DO
   IMPORT, não pelo nome da variável. Isso é determinístico: se o
   módulo importado é `axios`, o que vier dele é cliente HTTP,
   chame-se como se chamar.

3. Instâncias criadas a partir delas — `axios.create(...)` — são
   rastreadas como clientes também, porque é assim que a maioria
   dos projetos configura a base e os interceptadores.

O `HttpClient` do Angular não se chama pelo import: o framework
injeta a instância, e o código chama `this.http.get(url)`. O que o
identifica é o TIPO declarado na injeção, que é o import do módulo.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HttpClient:
    """Uma biblioteca cliente e como ela é chamada."""

    module: str
    methods: tuple[str, ...]
    factories: tuple[str, ...] = ()

    #: quando a própria função é chamada direto: `axios(config)`
    callable_directly: bool = False

    #: Cliente que não se chama pelo import, e sim pela instância que
    #: o framework injeta: o nome exportado que identifica o tipo.
    injected: str | None = None

    #: Métodos que recebem o verbo antes da URL:
    #: `http.request("GET", url)` no Angular.
    verb_first: tuple[str, ...] = ()


VERBS = (
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "head",
    "options",
)


CLIENTS = (
    HttpClient(
        module="axios",
        methods=VERBS + ("request",),
        factories=("create",),
        callable_directly=True,
    ),
    HttpClient(module="ky", methods=VERBS, factories=("create", "extend")),
    HttpClient(module="got", methods=VERBS, factories=("extend",)),
    HttpClient(module="superagent", methods=VERBS),
    HttpClient(module="redaxios", methods=VERBS, factories=("create",)),
    # https://angular.dev/api/common/http/HttpClient — injetado pelo
    # tipo, no construtor ou com `inject(HttpClient)`.
    HttpClient(
        module="@angular/common/http",
        methods=VERBS + ("jsonp", "request"),
        injected="HttpClient",
        verb_first=("request",),
    ),
)


#: Nomes globais que são chamada HTTP por si só, sem import.
PLATFORM = "fetch"

XHR_CONSTRUCTOR = "XMLHttpRequest"
