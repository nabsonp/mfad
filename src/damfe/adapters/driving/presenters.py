"""
Apresentação para terminal.

Todo o texto que o usuário lê nasce aqui, e só aqui. Os casos de
uso devolvem dados; traduzi-los em linhas é responsabilidade do
adaptador condutor. Trocar este arquivo por um que emita JSON não
toca em nenhuma regra da aplicação.
"""

from __future__ import annotations

from typing import Callable

from damfe.application.results import (
    ApiCallsResult,
    LlmSetupResult,
    StateAccessesResult,
    MicroFrontendsResult,
    CommunicationSetupResult,
    CommunicationsResult,
    DetectionResult,
    FragmentImportsResult,
    NavigationsResult,
    ReconstructionResult,
    VisualizationResult,
)
from damfe.domain import MicroFrontend


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


def fragment_imports(
    result: FragmentImportsResult,
    write: Writer,
) -> None:

    write("")
    write(f"{len(result.fragment_imports)} imports entre micro frontends")
    write("")

    for item in result.fragment_imports:

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
        slices.setdefault(item.path, set()).add(item.microfrontend)

    libraries = sorted({item.library for item in result.state_accesses})

    write(
        f"{len(result.state_accesses)} leituras do estado global "
        f"em {len(slices)} fatias ({', '.join(libraries)})"
    )
    write("")

    # As fatias lidas por mais de um micro frontend vêm primeiro:
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


def llm_setup(result: LlmSetupResult, write: Writer) -> None:

    settings = result.settings

    write("")
    write(f"  endereço  {settings.endpoint}")
    write(f"  modelo    {settings.model or '— não definido'}")
    write(f"  chave     {settings.masked_key}")
    write("")

    if result.written:
        write(f"Gravado em {result.written} com permissão 600.")
        write(
            "A chave fica no seu diretório de usuário, nunca no "
            "repositório analisado."
        )
    else:
        write("Nada alterado. Informe --key, --model ou --url para gravar.")

    if not settings.model:
        write("")
        write(
            "Defina um modelo para usar: "
            "damfe setup-llm --model <nome>"
        )


def reconstruction(result: ReconstructionResult, write: Writer) -> None:

    artifacts = result.artifacts

    write("")
    write(
        f"{len(artifacts.microfrontends)} micro frontends, "
        f"{len(artifacts.fragments)} fragmentos, "
        f"{len(artifacts.screens)} telas, "
        f"{len(artifacts.fragment_imports)} imports e "
        f"{len(artifacts.navigations)} navegações e "
        f"{len(artifacts.communications)} comunicações entre micro "
        f"frontends · {len(artifacts.api_calls)} chamadas externas · "
        f"{len(artifacts.state_accesses)} acessos ao estado global"
    )
    write("")

    for microfrontend in artifacts.microfrontends:
        _application(microfrontend, write)

    _written(result.written, write)


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
                f"{detection.rule}"
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
