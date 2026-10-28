"""
How the code makes HTTP calls.

Three layers, from the most generic to the most specific:

1. `fetch` and `XMLHttpRequest` are web platform API. They exist in
   any project, with any framework — it is the equivalent of
   `activeWhen` for routing: a hard contract, not a convention.

2. Known libraries are identified by the IMPORT SPECIFIER, not by the
   variable name. This is deterministic: if the imported module is
   `axios`, whatever comes from it is an HTTP client, whatever it is
   called.

3. Instances created from them — `axios.create(...)` — are tracked as
   clients too, because that is how most projects configure the base
   URL and the interceptors.

Angular's `HttpClient` is not called through the import: the framework
injects the instance, and the code calls `this.http.get(url)`. What
identifies it is the TYPE declared in the injection, which is the
module's import.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HttpClient:
    """A client library and how it is called."""

    module: str
    methods: tuple[str, ...]
    factories: tuple[str, ...] = ()

    #: when the function itself is called directly: `axios(config)`
    callable_directly: bool = False

    #: Client that is not called through the import, but through the
    #: instance the framework injects: the exported name that identifies the type.
    injected: str | None = None

    #: Methods that receive the verb before the URL:
    #: `http.request("GET", url)` in Angular.
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
    # https://angular.dev/api/common/http/HttpClient — injected by
    # type, in the constructor or with `inject(HttpClient)`.
    HttpClient(
        module="@angular/common/http",
        methods=VERBS + ("jsonp", "request"),
        injected="HttpClient",
        verb_first=("request",),
    ),
)


#: Global names that are an HTTP call by themselves, without an import.
PLATFORM = "fetch"

XHR_CONSTRUCTOR = "XMLHttpRequest"
