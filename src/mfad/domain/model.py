"""
The neutral model of architectural artifacts.

This module is the CONTRACT between the three CLI modules.
Nothing here may talk about single-spa, Module Federation or
any other framework: translating a framework's vocabulary into
these types is the job of the reconstruction module.

Framework-specific details, when worth keeping, go in the
`metadata` field of each entity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from mfad.domain.provenance import Provenance

if TYPE_CHECKING:
    from mfad.domain.communication import Communication


@dataclass
class SourceLocation:
    """Where something appears in the source code."""

    file: str
    line: int
    code: str | None = None


@dataclass
class Placement:
    """
    Where a piece of code is reached from: by which screens and by
    which fragments, following the micro frontend's internal imports.

    It is what allows asking whether two things happen on the SAME
    screen. A screen reaches its own code directly; another micro
    frontend's code only gets to it through a fragment that the
    screen renders — that is why fragments are kept apart, and
    whoever needs the complete screen follows the compositions.

    Empty means neither a screen nor a fragment reaches the file:
    dead code, or code that only the orchestrator mounts.
    """

    screens: list[str] = field(default_factory=list)
    fragments: list[str] = field(default_factory=list)


@dataclass
class RenderLocation:
    """Where a fragment is actually instantiated in the interface."""

    file: str
    line: int
    props: list[str] = field(default_factory=list)

    #: The screens in which this instantiation appears.
    #:
    #: Knowing that `mfe-checkout` consumes `DeliveryEstimateFragment`
    #: answers who depends on whom; knowing that it appears on the Cart
    #: screen answers WHERE it is seen, which is the question of whoever
    #: is going to change the system.
    #:
    #: More than one screen is a common and correct answer: the fragment
    #: may be in a shared component, reached from several. Empty means
    #: no screen reaches the file — instantiation in dead code, or in a
    #: file that only the shell mounts.
    screens: list[str] = field(default_factory=list)

    #: The fragments whose code reaches this instantiation.
    #:
    #: This is nesting: a fragment that renders another fragment.
    #: `screens` does not see this case, because the screen that renders
    #: the first fragment belongs to another micro frontend, and
    #: reachability does not cross the package boundary. Following this
    #: list from a screen's fragments returns everything that is mounted
    #: on it, at any depth.
    fragments: list[str] = field(default_factory=list)


@dataclass
class CodeSize:
    """
    Code size of a unit.

    `lines` is the physical count; `code_lines` discounts blank lines
    and lines that are only comments — the latter identified by the
    syntax tree, not by a text heuristic.
    """

    files: int = 0
    lines: int = 0
    code_lines: int = 0


@dataclass
class Fragment:
    """
    A unit of interface that an application exposes for
    others to consume.
    """

    name: str
    microfrontend: str
    file: str | None = None
    line: int = 0

    @property
    def id(self) -> str:
        return f"{self.microfrontend}#{self.name}"


@dataclass
class Screen:
    """A routable screen of an application."""

    component: str
    microfrontend: str
    route: str | None = None
    route_expression: str = ""
    file: str | None = None
    line: int = 0

    #: Whether the root component reaches the file that declares this screen.
    #:
    #: A screen declared in a file that nobody imports exists in the
    #: code and does not exist at runtime. Both things matter, and for
    #: different reasons: the reconstruction answers which screens the
    #: micro frontend defines, and this flag answers which of them are
    #: wired today. Deciding what to do with the difference is up to
    #: whoever reads the result — a disconnected screen is usually a
    #: half-done refactoring, not an extraction error.
    reachable: bool = True

    @property
    def id(self) -> str:
        return f"{self.microfrontend}#{self.component}"


@dataclass
class MicroFrontend:
    """
    An independent deployment unit — what single-spa calls a
    microfrontend and Module Federation calls a remote.

    `role` tells the orchestrator apart from the others.
    """

    id: str
    directory: str = ""
    entrypoint: str = ""
    routes: list[str] = field(default_factory=list)
    role: str = "microfrontend"

    #: The units this one mounts, when it is the orchestrator.
    #:
    #: A field, and not a `metadata` entry, because it is a contract:
    #: every technology has something that composes the others, and
    #: whoever writes a new reconstructor needs to see that in the port
    #: instead of discovering a key agreed upon somewhere. `metadata` is
    #: for what only makes sense within one technology.
    mounts: list[str] = field(default_factory=list)
    fragments: list[Fragment] = field(default_factory=list)
    screens: list[Screen] = field(default_factory=list)
    size: CodeSize = field(default_factory=CodeSize)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Composition:
    """
    Edge: one application consumes a fragment of another.

    Empty `renders` means an unused import — the fragment was
    imported but never instantiated.
    """

    consumer: str
    provider: str
    fragment: str
    local_name: str
    imported_at: SourceLocation
    renders: list[RenderLocation] = field(default_factory=list)


@dataclass
class ApiCall:
    """
    Edge: a micro frontend calls an external service.

    Unlike the others, this edge does not link two micro frontends —
    it links one of them to an address outside the system. The
    coupling appears when two of them consume the same endpoint.

    `path` is usually relative, because the base normally comes from
    an environment variable and cannot be determined statically.

    `screens` and `fragments` say who reaches the call by following
    the micro frontend's internal imports. They are lists because a
    shared service module is reached by several screens — and they
    are empty when the call is not reachable from any of them, which
    is also information.
    """

    microfrontend: str
    method: str
    path: str
    match: str
    client: str
    at: SourceLocation
    screens: list[str] = field(default_factory=list)
    fragments: list[str] = field(default_factory=list)


@dataclass
class Endpoint:
    """
    An external service consumed by the system.

    It is the only node of the model that lies OUTSIDE the boundary:
    nobody deploys it, nobody versions it alongside, and still two
    micro frontends that call it are coupled through its contract.
    Without it, that coupling had nowhere to live — `ApiCall` kept
    the path as text, and the "same endpoint" of `hammering-apis`
    was not a thing, it was a string coincidence.

    Derived from the calls, not extracted: the path is the identity,
    and the methods are the verbs seen on it.
    """

    path: str
    methods: list[str] = field(default_factory=list)

    #: who calls it, by identifier
    microfrontends: list[str] = field(default_factory=list)


@dataclass
class StateAccess:
    """
    A micro frontend accesses a part of the global state.

    Coupling without a message and without an import: two micro
    frontends that touch the same slice depend on the same data
    shape, and a change to it breaks both — even if they do not know
    each other.

    In state libraries, only reads go in. Writes also couple, but
    what the code reveals at the call site is the name of the
    dispatched action, not the altered slice — finding the slice
    would require following the reducer, which may live in another
    package.

    In browser storage writes go in, because there they reveal the
    slice: `setItem("token", …)` tells the key as much as
    `getItem("token")`. `access` distinguishes the two.
    """

    microfrontend: str
    library: str
    path: str
    at: SourceLocation

    #: `read` or `write`
    access: str = "read"


@dataclass
class Navigation:
    """
    Edge: code of one application takes the user to a route
    belonging to another.

    `match` tells the degree of confidence: `exact` when the URL was
    fully resolved, `prefix` when only its beginning could be
    determined statically.
    """

    source: str
    target: str
    expression: str
    resolved_url: str | None
    match: str
    at: SourceLocation

    #: Screens and fragments that reach the navigating code.
    #:
    #: It is the ORIGIN side seen as a place: the "Checkout" button is
    #: on the cart screen. The destination is the route, which already
    #: tells the arrival screen.
    on: Placement = field(default_factory=Placement)


@dataclass
class MicroFrontendArchitecture:
    """Everything the reconstruction extracted from a repository."""

    #: name of the analyzed project, to identify the report.
    #: Only the name, never the absolute path — the artifact is
    #: versioned, and a machine path would pollute the diff.
    project: str = ""
    microfrontends: list[MicroFrontend] = field(default_factory=list)
    compositions: list[Composition] = field(default_factory=list)
    navigations: list[Navigation] = field(default_factory=list)
    communications: list["Communication"] = field(default_factory=list)
    api_calls: list[ApiCall] = field(default_factory=list)
    state_accesses: list[StateAccess] = field(default_factory=list)

    #: Where this came from: schema version, tool version,
    #: extractor used and the revision of each repository read.
    provenance: "Provenance" = field(default_factory=Provenance)

    def microfrontend(self, identifier: str) -> MicroFrontend | None:

        for microfrontend in self.microfrontends:

            if microfrontend.id == identifier:
                return microfrontend

        return None

    @property
    def fragments(self) -> list[Fragment]:

        return [
            fragment
            for microfrontend in self.microfrontends
            for fragment in microfrontend.fragments
        ]

    @property
    def endpoints(self) -> list["Endpoint"]:
        """
        The external services, grouped by the calls.

        Derived, like `fragments` and `screens`: it is not a stored
        collection, it is the reading of the calls by path.
        """

        grouped: dict[str, Endpoint] = {}

        for call in self.api_calls:

            endpoint = grouped.setdefault(call.path, Endpoint(path=call.path))

            if call.method not in endpoint.methods:
                endpoint.methods.append(call.method)

            if call.microfrontend not in endpoint.microfrontends:
                endpoint.microfrontends.append(call.microfrontend)

        return [grouped[path] for path in sorted(grouped)]

    @property
    def screens(self) -> list[Screen]:

        return [
            screen
            for microfrontend in self.microfrontends
            for screen in microfrontend.screens
        ]
