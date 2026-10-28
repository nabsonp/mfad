"""
Driving adapter: command line.

Single responsibility: translate arguments into a use case, execute
it, hand the result to the presenter and map failure into an exit
code. No rule lives here.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mfad import __version__
from mfad.adapters.driven.storage import SETUP_DIRECTORY
from mfad.adapters.driving import presenters
from mfad.application.errors import ApplicationError
from mfad.composition import Container


#: The collections that `reconstruct --only` can extract on their own.
#:
#: They were six subcommands until they became a flag: they were
#: slices of the same process, exposed as if they were different
#: commands, and made the program's help list eleven entries for a
#: three-step flow.
EXTRACTIONS = {
    "microfrontends": "_applications",
    "compositions": "_compositions",
    "navigations": "_navigations",
    "api-calls": "_api_calls",
    "global-state": "_global_state",
    "communications": "_communications",
}


def build_parser() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(
        prog="mfad",
        description=(
            "Static analysis of micro frontend architectures: "
            "reconstruction, anti-pattern detection and visualization."
        ),
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"mfad {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    def with_source(subparser):
        subparser.add_argument("repository", type=Path)
        subparser.add_argument("--framework")
        subparser.add_argument(
            "--prefix",
            help="Organization prefix, e.g. @nabstore/",
        )
        return subparser

    # ------------------------------------------------------ reconstruct
    reconstruct = with_source(
        subparsers.add_parser(
            "reconstruct",
            help="Extracts all the architectural artifacts.",
        )
    )
    reconstruct.add_argument("--out", type=Path, default=Path("artifacts"))
    reconstruct.add_argument(
        "--only",
        choices=sorted(EXTRACTIONS),
        help=(
            "Extracts a single collection instead of all of them. A slice of "
            "the same process, useful to debug an extractor."
        ),
    )
    reconstruct.add_argument(
        "--spec",
        type=Path,
        help=(
            "Path of the communication declaration. By default, "
            f"<repo>/{SETUP_DIRECTORY}/"
        ),
    )

    # ---------------------------------------------------------- analyze
    analyze = with_source(
        subparsers.add_parser(
            "analyze",
            help="Reconstructs, detects and visualizes in a single pass.",
        )
    )
    analyze.add_argument("--out", type=Path, default=Path("artifacts"))
    analyze.add_argument("--spec", type=Path)
    analyze.add_argument("--rule", action="append")
    analyze.add_argument("--format", default="html")

    # --------------------------------------------- setup-communication
    setup = subparsers.add_parser(
        "setup-communication",
        help="Declares how the micro frontends communicate.",
    )
    setup.add_argument("repository", type=Path)
    setup.add_argument(
        "--out",
        type=Path,
        help=(
            "Where to write the declaration. By default, "
            f"<repo>/{SETUP_DIRECTORY}/"
        ),
    )

    # ----------------------------------------------------------- detect
    detect = subparsers.add_parser(
        "detect",
        help="Detects anti-patterns over the artifacts.",
    )
    detect.add_argument(
        "artifacts",
        type=Path,
        nargs="?",
        default=Path("artifacts"),
    )
    detect.add_argument("--out", type=Path)
    detect.add_argument("--rule", action="append")

    # -------------------------------------------------------- visualize
    visualize = subparsers.add_parser(
        "visualize",
        help="Generates the architecture visualization.",
    )
    visualize.add_argument(
        "artifacts",
        type=Path,
        nargs="?",
        default=Path("artifacts"),
    )
    visualize.add_argument("--out", type=Path)
    visualize.add_argument("--detections", type=Path)
    visualize.add_argument("--format", default="html")

    return parser


def main(argv: list[str] | None = None) -> int:

    arguments = build_parser().parse_args(argv)

    def write(message: str = "") -> None:
        print(message)

    container = Container()

    extractors = {
        "microfrontends": _applications,
        "compositions": _compositions,
        "navigations": _navigations,
        "api-calls": _api_calls,
        "global-state": _global_state,
        "communications": _communications,
    }

    if arguments.command == "reconstruct" and arguments.only:
        handler = extractors[arguments.only]
    else:
        handler = {
            "reconstruct": _reconstruct,
            "analyze": _analyze,
            "setup-communication": _setup_communication,
            "detect": _detect,
            "visualize": _visualize,
        }[arguments.command]

    try:
        return handler(container, arguments, write)

    except ApplicationError as error:
        write(str(error))
        return 1

    except KeyError as error:
        write(str(error.args[0] if error.args else error))
        return 2


# ----------------------------------------------------------------------


def _reconstructor(container, arguments, write):

    chosen = container.reconstructor(
        framework=arguments.framework,
        repository_path=arguments.repository,
        organization_prefix=arguments.prefix,
    )

    if not chosen:
        write(
            "No extractor recognized the repository. "
            "Use --framework to force one."
        )

        return chosen

    excluded = container.excluded_packages(arguments.repository)

    if excluded:
        write(
            f"{len(excluded)} package(s) left out of the analysis, built on "
            "a platform with its own integration:"
        )

        for path, platform in excluded.items():
            write(f"  {path} — {platform}")

    return chosen


def _reconstruct(container, arguments, write) -> int:

    reconstructor = _reconstructor(container, arguments, write)

    if not reconstructor:
        return 1

    write(
        f"Reconstructing {arguments.repository} "
        f"with the {reconstructor.name} extractor"
    )

    result = container.reconstruct(
        repository_path=arguments.repository,
        destination=arguments.out,
        reconstructor=reconstructor,
    ).execute()

    presenters.reconstruction(result, write)

    return 0


def _applications(container, arguments, write) -> int:

    reconstructor = _reconstructor(container, arguments, write)

    if not reconstructor:
        return 1

    result = container.extract_microfrontends(
        repository_path=arguments.repository,
        reconstructor=reconstructor,
    ).execute()

    presenters.microfrontends(result, write)

    return 0


def _compositions(container, arguments, write) -> int:

    reconstructor = _reconstructor(container, arguments, write)

    if not reconstructor:
        return 1

    result = container.extract_compositions(
        repository_path=arguments.repository,
        reconstructor=reconstructor,
    ).execute()

    presenters.compositions(result, write)

    return 0


def _navigations(container, arguments, write) -> int:

    reconstructor = _reconstructor(container, arguments, write)

    if not reconstructor:
        return 1

    result = container.extract_navigations(
        repository_path=arguments.repository,
        reconstructor=reconstructor,
    ).execute()

    presenters.navigations(result, write)

    return 0


def _api_calls(container, arguments, write) -> int:

    reconstructor = _reconstructor(container, arguments, write)

    if not reconstructor:
        return 1

    result = container.extract_api_calls(
        repository_path=arguments.repository,
        reconstructor=reconstructor,
    ).execute()

    presenters.api_calls(result, write)

    return 0


def _global_state(container, arguments, write) -> int:

    reconstructor = _reconstructor(container, arguments, write)

    if not reconstructor:
        return 1

    result = container.extract_state_accesses(
        repository_path=arguments.repository,
        reconstructor=reconstructor,
    ).execute()

    presenters.state_accesses(result, write)

    return 0


def _communications(container, arguments, write) -> int:

    reconstructor = _reconstructor(container, arguments, write)

    if not reconstructor:
        return 1

    result = container.extract_communications(
        repository_path=arguments.repository,
        spec_path=arguments.spec or arguments.repository,
        reconstructor=reconstructor,
    ).execute()

    presenters.communications(result, write)

    return 0


def _setup_communication(container, arguments, write) -> int:

    result = container.setup_communication(
        destination=arguments.out or arguments.repository,
    ).execute()

    presenters.communication_setup(result, write)

    return 0


def _detect(container, arguments, write) -> int:

    result = container.detect(
        source=arguments.artifacts,
        destination=arguments.out,
        rules=container.rules(arguments.rule),
    ).execute()

    presenters.detection(result, write)

    return 0


def _destination(arguments) -> Path | None:
    """
    Where the visualization is written when --out was not given.

    Text formats go to standard output, which is where they are
    useful: mermaid exists to be pasted into a document. HTML does not
    — it is hundreds of kilobytes in a single file, and dumping it to
    the terminal forces the user to copy from the screen what the
    command already had ready. That is why it gets a default path
    inside the artifacts folder.
    """

    if arguments.out:
        return arguments.out

    if arguments.format == "html":
        return arguments.artifacts / "architecture.html"

    return None


def _analyze(container, arguments, write) -> int:
    """
    The three steps in a single call.

    It is almost everyone's use case, and until now it required
    getting three commands right, in order, knowing that `detect`
    reads what `reconstruct` wrote and that `visualize` needs
    `--detections`. That chaining is a detail of the tool, not a
    decision of the user.
    """

    reconstructor = _reconstructor(container, arguments, write)

    if not reconstructor:
        return 1

    write(
        f"Reconstructing {arguments.repository} "
        f"with the {reconstructor.name} extractor"
    )

    reconstruction = container.reconstruct(
        repository_path=arguments.repository,
        destination=arguments.out,
        reconstructor=reconstructor,
    ).execute()

    presenters.reconstruction(reconstruction, write)

    write()

    detection = container.detect(
        source=arguments.out,
        destination=arguments.out,
        rules=container.rules(arguments.rule),
    ).execute()

    presenters.detection(detection, write)

    write()

    visualization = container.visualize(
        source=arguments.out,
        destination=(
            arguments.out / "architecture.html"
            if arguments.format == "html"
            else None
        ),
        renderer_name=arguments.format,
        detections_path=arguments.out,
    ).execute()

    presenters.visualization(visualization, write)

    return 0


def _visualize(container, arguments, write) -> int:

    result = container.visualize(
        source=arguments.artifacts,
        destination=_destination(arguments),
        renderer_name=arguments.format,
        detections_path=arguments.detections,
    ).execute()

    presenters.visualization(result, write)

    return 0


if __name__ == "__main__":
    sys.exit(main())
