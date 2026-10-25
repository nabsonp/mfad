"""
Apresentação para terminal.

Todo o texto que o usuário lê nasce aqui, e só aqui. Os casos de
uso devolvem dados; traduzi-los em linhas é responsabilidade do
adaptador condutor. Trocar este arquivo por um que emita JSON não
toca em nenhuma regra da aplicação.
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

    write(f"  rotas:      {', '.join(microfrontend.routes) or DASH}")

    write(
        f"  tamanho:    {microfrontend.size.code_lines} linhas de código "
        f"em {microfrontend.size.files} arquivos"
    )

    write(
        "  fragmentos: "
        + (
            ", ".join(item.name for item in microfrontend.fragments)
            or DASH
        )
    )

    write(
        "  telas:      "
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
    write(f"{len(result.compositions)} imports entre micro frontends")
    write("")

    for item in result.compositions:

        write(f"{item.consumer} → {item.provider} : {item.fragment}")

        write(
            f"  importado em:   "
            f"{item.imported_at.file}:{item.imported_at.line}"
        )

        if not item.renders:
            write("  renderizado em: — (importado, nunca instanciado)")

        for render in item.renders:

            props = ", ".join(render.props) or DASH

            write(
                f"  renderizado em: "
                f"{render.file}:{render.line}  props: {props}"
            )

        write("")


def navigations(result: NavigationsResult, write: Writer) -> None:

    write("")
    write(f"{len(result.navigations)} navegações entre micro frontends")
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
        f"{len(result.communications)} comunicações entre micro frontends"
    )

    if not result.configured:
        write(
            "  (nenhum mecanismo próprio declarado — só primitivas da "
            "plataforma e barramentos conhecidos)"
        )
    write("")

    for item in result.communications:

        write(
            f"{item.source} → {item.target}  "
            f"[{item.mechanism}] canal: {item.channel}"
        )

        for location in item.produced_at:
            write(f"  publica  {location.file}:{location.line}")

        for location in item.consumed_at:
            write(f"  assina   {location.file}:{location.line}")

        write("")


def communication_setup(
    result: CommunicationSetupResult,
    write: Writer,
) -> None:

    write("")
    write(f"Declaração gravada em: {result.written}")

    if not result.spec:
        write("")
        write(
            "É um modelo comentado. Edite com as funções reais do "
            "seu projeto — a extração usa exatamente o que estiver "
            "declarado ali."
        )


def api_calls(result: ApiCallsResult, write: Writer) -> None:

    write("")

    endpoints: dict[tuple[str, str], set[str]] = {}

    for item in result.api_calls:
        endpoints.setdefault(
            (item.method, item.path), set()
        ).add(item.microfrontend)

    write(
        f"{len(result.api_calls)} chamadas a "
        f"{len(endpoints)} endpoints distintos"
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
        write("Nenhum estado global encontrado.")
        return

    slices: dict[str, set[str]] = {}

    for item in result.state_accesses:
        slices.setdefault(f"{item.library}:{item.path}", set()).add(
            item.microfrontend
        )

    libraries = sorted({item.library for item in result.state_accesses})

    write(
        f"{len(result.state_accesses)} acessos ao estado global "
        f"em {len(slices)} fatias ({', '.join(libraries)})"
    )
    write("")

    # As fatias acessadas por mais de um micro frontend vêm primeiro:
    # são elas que caracterizam acoplamento.
    for path, readers in sorted(
        slices.items(),
        key=lambda item: (-len(item[1]), item[0]),
    ):

        names = ", ".join(
            sorted(reader.rpartition("/")[2] for reader in readers)
        )

        write(f"{path}")
        write(f"    lido por {len(readers)}: {names}")

    write("")


def reconstruction(result: ReconstructionResult, write: Writer) -> None:

    architecture = result.architecture

    write("")
    write(
        f"{len(architecture.microfrontends)} micro frontends, "
        f"{len(architecture.fragments)} fragmentos, "
        f"{len(architecture.screens)} telas, "
        f"{len(architecture.compositions)} imports e "
        f"{len(architecture.navigations)} navegações e "
        f"{len(architecture.communications)} comunicações entre micro "
        f"frontends · {len(architecture.api_calls)} chamadas externas · "
        f"{len(architecture.state_accesses)} acessos ao estado global"
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
            f"  aviso: o mecanismo declarado {name!r} não produziu "
            "comunicação nenhuma"
        )

    write(
        "  verifique se `module` bate com o especificador real do "
        "import, e se os dois lados existem no código"
    )
    write("")


def detection(result: DetectionResult, write: Writer) -> None:

    write("")

    if not result.detections:

        write(
            f"Nenhum anti-padrão encontrado "
            f"({result.rules_applied} regras aplicadas)."
        )

    else:

        write(
            f"{len(result.detections)} ocorrências "
            f"({result.rules_applied} regras aplicadas):"
        )

        write("")

        for detection in result.detections:

            write(
                f"{detection.anti_pattern}"
                + (f"  [{detection.dimension}]" if detection.dimension else "")
            )
            write(f"  {detection.message}")

            for location in detection.locations:
                write(f"  em {location.file}:{location.line}")

            write("")

    _written([result.written] if result.written else [], write)


def visualization(result: VisualizationResult, write: Writer) -> None:

    if result.written:
        _written([result.written], write)
        return

    write(result.output)


def _written(paths, write: Writer) -> None:

    for path in paths:
        write(f"  gravado: {path}")
