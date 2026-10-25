"""
Adaptador condutor: linha de comando.

Responsabilidade única: traduzir argumentos em um caso de uso,
executá-lo, entregar o resultado ao apresentador e mapear falha
em código de saída. Nenhuma regra mora aqui.
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


#: As coleções que `reconstruct --only` sabe extrair sozinhas.
#:
#: Foram seis subcomandos até virarem uma flag: eram recorte do mesmo
#: processo, expostos como se fossem comandos diferentes, e faziam a
#: ajuda do programa listar onze entradas para um fluxo de três passos.
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
            "Análise estática de arquiteturas micro frontend: "
            "reconstrução, detecção de anti-padrões e visualização."
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
            help="Prefixo da organização, ex.: @nabstore/",
        )
        return subparser

    # ------------------------------------------------------ reconstruct
    reconstruct = with_source(
        subparsers.add_parser(
            "reconstruct",
            help="Extrai todos os artefatos arquiteturais.",
        )
    )
    reconstruct.add_argument("--out", type=Path, default=Path("artifacts"))
    reconstruct.add_argument(
        "--only",
        choices=sorted(EXTRACTIONS),
        help=(
            "Extrai só uma coleção, em vez de todas. Recorte do mesmo "
            "processo, útil para depurar um extrator."
        ),
    )
    reconstruct.add_argument(
        "--spec",
        type=Path,
        help=(
            "Caminho da declaração de comunicação. Por padrão, "
            f"<repo>/{SETUP_DIRECTORY}/"
        ),
    )

    # ---------------------------------------------------------- analyze
    analyze = with_source(
        subparsers.add_parser(
            "analyze",
            help="Reconstrói, detecta e visualiza numa só passada.",
        )
    )
    analyze.add_argument("--out", type=Path, default=Path("artifacts"))
    analyze.add_argument("--spec", type=Path)
    analyze.add_argument("--rule", action="append")
    analyze.add_argument("--format", default="html")

    # --------------------------------------------- setup-communication
    setup = subparsers.add_parser(
        "setup-communication",
        help="Declara como os micro frontends se comunicam.",
    )
    setup.add_argument("repository", type=Path)
    setup.add_argument(
        "--out",
        type=Path,
        help=(
            "Onde gravar a declaração. Por padrão, "
            f"<repo>/{SETUP_DIRECTORY}/"
        ),
    )

    # ----------------------------------------------------------- detect
    detect = subparsers.add_parser(
        "detect",
        help="Detecta anti-padrões sobre os artefatos.",
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
        help="Gera a visualização da arquitetura.",
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
            "Nenhum extrator reconheceu o repositório. "
            "Use --framework para forçar um."
        )

        return chosen

    excluded = container.excluded_packages(arguments.repository)

    if excluded:
        write(
            f"{len(excluded)} pacote(s) fora da análise, construídos sobre "
            "plataforma com integração própria:"
        )

        for path, platform in excluded.items():
            write(f"  {path} — {platform}")

    return chosen


def _reconstruct(container, arguments, write) -> int:

    reconstructor = _reconstructor(container, arguments, write)

    if not reconstructor:
        return 1

    write(
        f"Reconstruindo {arguments.repository} "
        f"com o extrator {reconstructor.name}"
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
    Onde a visualização é gravada quando --out não foi informado.

    Formatos de texto vão para a saída padrão, que é onde servem: o
    mermaid existe para ser colado num documento. O HTML não — são
    centenas de kilobytes num arquivo único, e despejá-los no terminal
    obriga o usuário a copiar da tela o que o comando já tinha pronto.
    Por isso ele ganha um caminho padrão dentro da pasta de artefatos.
    """

    if arguments.out:
        return arguments.out

    if arguments.format == "html":
        return arguments.artifacts / "architecture.html"

    return None


def _analyze(container, arguments, write) -> int:
    """
    Os três passos numa chamada só.

    É o caso de uso de quase todo mundo, e até aqui exigia acertar
    três comandos em ordem sabendo que `detect` lê o que `reconstruct`
    escreveu e que `visualize` precisa de `--detections`. Esse
    encadeamento é detalhe da ferramenta, não decisão do usuário.
    """

    reconstructor = _reconstructor(container, arguments, write)

    if not reconstructor:
        return 1

    write(
        f"Reconstruindo {arguments.repository} "
        f"com o extrator {reconstructor.name}"
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
