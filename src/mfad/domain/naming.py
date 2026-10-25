"""
Como cada micro frontend se chama nos artefatos.

O extrator conhece o micro frontend pelo nome que a tecnologia usa
para carregá-lo: o `name` do `registerApplication` ou do
`ModuleFederationPlugin`. Quem lê o resultado o procura pelo
repositório, ou pela pasta dentro do monorepo, e o nome registrado
muitas vezes não se parece com ela (`mf-tipo-inscripcion` dentro de
`sga_cliente_administracion_mf`). O identificador passa a ser o
diretório; o nome registrado fica em `metadata["registered_name"]`.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from mfad.domain.model import MicroFrontend, MicroFrontendArchitecture


def distinct(microfrontends: list[MicroFrontend]) -> None:
    """
    Unidades registradas com o mesmo nome — sete orquestradores, cada um
    no seu repositório, todos `@org/root-config` — recebem já o nome do
    diretório, antes de qualquer relação ser extraída. Depois não há
    mais como separá-las: tudo o que cada uma faz sairia com o mesmo id.
    """

    counts: dict[str, int] = {}

    for item in microfrontends:
        counts[item.id] = counts.get(item.id, 0) + 1

    repeated = [item for item in microfrontends if counts[item.id] > 1 and item.directory]

    if not repeated:
        return

    last = [PurePosixPath(item.directory).name for item in repeated]

    for item, name in zip(repeated, last):
        item.metadata["registered_name"] = item.id
        item.id = name if last.count(name) == 1 else item.directory


def by_directory(architecture: MicroFrontendArchitecture) -> None:
    """Troca o identificador de cada micro frontend pelo do seu diretório, em todas as referências."""

    mapping = _names(architecture)

    if not mapping:
        return

    def name(identifier: str) -> str:
        return mapping.get(identifier, identifier)

    for microfrontend in architecture.microfrontends:

        if microfrontend.id in mapping:
            microfrontend.metadata["registered_name"] = microfrontend.id
            microfrontend.id = mapping[microfrontend.id]

        microfrontend.mounts = [name(item) for item in microfrontend.mounts]

        if "remotes" in microfrontend.metadata:
            microfrontend.metadata["remotes"] = [name(item) for item in microfrontend.metadata["remotes"]]

        for item in microfrontend.fragments + microfrontend.screens:
            item.microfrontend = name(item.microfrontend)

    for composition in architecture.compositions:
        composition.consumer = name(composition.consumer)
        composition.provider = name(composition.provider)

    for item in architecture.navigations + architecture.communications:
        item.source = name(item.source)
        item.target = name(item.target)

    for item in architecture.api_calls + architecture.state_accesses:
        item.microfrontend = name(item.microfrontend)


def _names(architecture: MicroFrontendArchitecture) -> dict[str, str]:
    """
    Nome registrado → último segmento do diretório. Se dois diretórios
    terminam igual (`a/app` e `b/app`), os dois ficam com o caminho
    inteiro; sem diretório, fica o nome registrado.
    """

    last = {item.id: PurePosixPath(item.directory).name for item in architecture.microfrontends if item.directory}

    counts: dict[str, int] = {}

    for value in last.values():
        counts[value] = counts.get(value, 0) + 1

    chosen = {
        identifier: value if counts[value] == 1 else next(item.directory for item in architecture.microfrontends if item.id == identifier)
        for identifier, value in last.items()
    }

    taken = set(chosen.values())

    # Um nome registrado sem diretório que coincida com o de outro
    # diretório ficaria ambíguo: quem não muda de nome não pode colidir.
    unchanged = {item.id for item in architecture.microfrontends if item.id not in chosen}

    return {
        identifier: value
        for identifier, value in chosen.items()
        if value != identifier and value not in unchanged and list(chosen.values()).count(value) == 1
    } if taken else {}
