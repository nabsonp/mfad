"""
Terminal presentation.

All the text the user reads is born here, and only here. The use
cases return data; turning it into lines is the driving adapter's
responsibility. Swapping this file for one that emits JSON touches
no application rule.
"""

from __future__ import annotations

from typing import Callable

from mfad.application.results import (
    ApiCallsResult,
    StateAccessesResult,
    MicroFrontendsResult,
    CommunicationSetupResult,
    CommunicationsResult,
    DetectionResult,
    CompositionsResult,
    NavigationsResult,
    ReconstructionResult,
    VisualizationResult,
)
from mfad.domain import MicroFrontend


Writer = Callable[[str], None]

DASH = "—"


def microfrontends(result: MicroFrontendsResult, write: Writer) -> None:

    write("")
    write(f"{len(result.microfrontends)} micro frontends")
    write("")

    for microfrontend in result.microfrontends:
        _application(microfrontend, write)


def _application(microfrontend: MicroFrontend, write: Writer) -> None:

    marker = " (shell)" if microfrontend.role == "shell" else ""

    write(f"{microfrontend.id}{marker}")

    write(f"  routes:     {', '.join(microfrontend.routes) or DASH}")

    write(
        f"  size:       {microfrontend.size.code_lines} lines of code "
        f"in {microfrontend.size.files} files"
    )

    write(
        "  fragments:  "
        + (
            ", ".join(item.name for item in microfrontend.fragments)
            or DASH
        )
    )

    write(
        "  screens:    "
        + (
            ", ".join(item.component for item in microfrontend.screens)
            or DASH
        )
    )

    write("")


def compositions(
    result: CompositionsResult,
    write: Writer,
) -> None:

    write("")
    write(f"{len(result.compositions)} imports between micro frontends")
    write("")

    for item in result.compositions:

        write(f"{item.consumer} → {item.provider} : {item.fragment}")

        write(
            f"  imported at:    "
            f"{item.imported_at.file}:{item.imported_at.line}"
        )

        if not item.renders:
            write("  rendered at:    — (imported, never instantiated)")

        for render in item.renders:

            props = ", ".join(render.props) or DASH

            write(
                f"  rendered at:    "
                f"{render.file}:{render.line}  props: {props}"
            )

        write("")


def navigations(result: NavigationsResult, write: Writer) -> None:

    write("")
    write(f"{len(result.navigations)} navigations between micro frontends")
    write("")

    for item in result.navigations:

        write(f"{item.source} → {item.target}")

        write(
            f"  {item.at.file}:{item.at.line}"
        )

        write(
            f"  {item.expression}  ⇒  {item.resolved_url}  ({item.match})"
        )

        write("")


def communications(result: CommunicationsResult, write: Writer) -> None:

    write("")

    write(
        f"{len(result.communications)} communications between micro frontends"
    )

    if not result.configured:
        write(
            "  (no custom mechanism declared — only platform "
            "primitives and known buses)"
        )
    write("")

    for item in result.communications:

        write(
            f"{item.source} → {item.target}  "
            f"[{item.mechanism}] channel: {item.channel}"
        )

        for location in item.produced_at:
            write(f"  publishes  {location.file}:{location.line}")

        for location in item.consumed_at:
            write(f"  subscribes {location.file}:{location.line}")

        write("")


def communication_setup(
    result: CommunicationSetupResult,
    write: Writer,
) -> None:

    write("")
    write(f"Declaration written to: {result.written}")

    if not result.spec:
        write("")
        write(
            "It is a commented template. Edit it with your project's real "
            "functions — the extraction uses exactly what is "
            "declared there."
        )


def api_calls(result: ApiCallsResult, write: Writer) -> None:

    write("")

    endpoints: dict[tuple[str, str], set[str]] = {}

    for item in result.api_calls:
        endpoints.setdefault(
            (item.method, item.path), set()
        ).add(item.microfrontend)

    write(
        f"{len(result.api_calls)} calls to "
        f"{len(endpoints)} distinct endpoints"
    )
    write("")

    for (method, path), callers in sorted(endpoints.items()):

        names = ", ".join(
            sorted(caller.rpartition("/")[2] for caller in callers)
        )

        write(f"{method:7} {path}")
        write(f"        {names}")

    write("")


def state_accesses(result: StateAccessesResult, write: Writer) -> None:

    write("")

    if not result.state_accesses:
        write("No global state found.")
        return

    slices: dict[str, set[str]] = {}

    for item in result.state_accesses:
        slices.setdefault(f"{item.library}:{item.path}", set()).add(
            item.microfrontend
        )

    libraries = sorted({item.library for item in result.state_accesses})

    write(
        f"{len(result.state_accesses)} global state accesses "
        f"in {len(slices)} slices ({', '.join(libraries)})"
    )
    write("")

    # The slices accessed by more than one micro frontend come first:
    # they are what characterizes coupling.
    for path, readers in sorted(
        slices.items(),
        key=lambda item: (-len(item[1]), item[0]),
    ):

        names = ", ".join(
            sorted(reader.rpartition("/")[2] for reader in readers)
        )

        write(f"{path}")
        write(f"    read by {len(readers)}: {names}")

    write("")


def reconstruction(result: ReconstructionResult, write: Writer) -> None:

    architecture = result.architecture

    write("")
    write(
        f"{len(architecture.microfrontends)} micro frontends, "
        f"{len(architecture.fragments)} fragments, "
        f"{len(architecture.screens)} screens, "
        f"{len(architecture.compositions)} imports, "
        f"{len(architecture.navigations)} navigations and "
        f"{len(architecture.communications)} communications between micro "
        f"frontends · {len(architecture.api_calls)} external calls · "
        f"{len(architecture.state_accesses)} global state accesses"
    )
    write("")

    _unmatched(result.unmatched, write)

    for microfrontend in architecture.microfrontends:
        _application(microfrontend, write)

    _written(result.written, write)


def _unmatched(names: list[str], write: Writer) -> None:

    if not names:
        return

    for name in names:
        write(
            f"  warning: the declared mechanism {name!r} produced no "
            "communication"
        )

    write(
        "  check that `module` matches the real import specifier, "
        "and that both sides exist in the code"
    )
    write("")


def detection(result: DetectionResult, write: Writer) -> None:

    write("")

    if not result.detections:

        write(
            f"No anti-pattern found "
            f"({result.rules_applied} rules applied)."
        )

    else:

        write(
            f"{len(result.detections)} occurrences "
            f"({result.rules_applied} rules applied):"
        )

        write("")

        for detection in result.detections:

            write(
                f"{detection.anti_pattern}"
                + (f"  [{detection.dimension}]" if detection.dimension else "")
            )
            write(f"  {detection.message}")

            for location in detection.locations:
                write(f"  at {location.file}:{location.line}")

            write("")

    _written([result.written] if result.written else [], write)


def visualization(result: VisualizationResult, write: Writer) -> None:

    if result.written:
        _written([result.written], write)
        return

    write(result.output)


def _written(paths, write: Writer) -> None:

    for path in paths:
        write(f"  written: {path}")
