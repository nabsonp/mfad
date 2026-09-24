"""
Tela que agrega fragmentos de vários micro frontends.

Uma tela assim vira ponto de convergência: falha, mudança de
contrato ou indisponibilidade em qualquer um dos provedores
aparece ali. E quem mantém a tela precisa acompanhar a evolução
de todos eles.

O sinal é a QUANTIDADE DE PROVEDORES DISTINTOS, não a de
fragmentos. Uma tela com três fragmentos do mesmo micro frontend
tem um fornecedor só — é reúso, não concentração de dependência.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from damfe.application.ports import Rule
from damfe.domain import AntiPatternDetection, ArtifactSet, SourceLocation


@dataclass
class Host:
    """O que uma tela hospeda de fora."""

    screen: str
    owner: str
    providers: set[str] = field(default_factory=set)
    fragments: list[str] = field(default_factory=list)
    locations: list[SourceLocation] = field(default_factory=list)


class HubLikeDependency(Rule):

    name = "hub-like-dependency"

    description = (
        "Tela que instancia fragmentos de vários micro frontends "
        "distintos, concentrando dependências num só ponto."
    )

    def __init__(self, min_providers: int = 2):

        #: A partir de quantos provedores distintos a tela é
        #: considerada um hub. Dois já indica convergência; times
        #: com muitos micro frontends podem querer subir isso.
        self.min_providers = min_providers

    def check(self, artifacts: ArtifactSet) -> list[AntiPatternDetection]:

        hosts = self._hosts(artifacts)

        return [
            self._detection(host)
            for host in hosts.values()
            if len(host.providers) >= self.min_providers
        ]

    def _hosts(self, artifacts: ArtifactSet) -> dict[str, Host]:
        """
        Agrupa os fragmentos instanciados por tela.

        A ligação é pelo ARQUIVO: um fragmento pertence à tela cujo
        arquivo o instancia. Fragmento renderizado dentro de um
        componente auxiliar, e não no arquivo da tela, não é
        atribuído — ver a limitação registrada no README.
        """

        screens = {
            screen.file: screen
            for microfrontend in artifacts.microfrontends
            for screen in microfrontend.screens
            if screen.file
        }

        hosts: dict[str, Host] = {}

        for item in artifacts.fragment_imports:

            for render in item.renders:

                screen = screens.get(render.file)

                if not screen:
                    continue

                host = hosts.setdefault(
                    screen.id,
                    Host(
                        screen=screen.component,
                        owner=screen.microfrontend,
                    ),
                )

                host.providers.add(item.provider)
                host.fragments.append(item.fragment)
                host.locations.append(
                    SourceLocation(file=render.file, line=render.line)
                )

        return hosts

    def _detection(self, host: Host) -> AntiPatternDetection:

        providers = sorted(host.providers)

        return AntiPatternDetection(
            rule=self.name,
            dimension="composição",
            explanation=(
                "A tela instancia fragmentos de mais de um micro "
                "frontend, concentrando num só ponto as falhas e as "
                "mudanças de contrato de todos eles."
            ),
            message=(
                f"A tela {host.screen}, de {self._short(host.owner)}, "
                f"agrega {len(host.fragments)} fragmentos de "
                f"{len(providers)} micro frontends: "
                + ", ".join(self._short(item) for item in providers)
            ),
            subjects=[host.owner, *providers],
            locations=host.locations,
            metadata={
                "edges": [
                    [host.owner, provider] for provider in providers
                ],
                "screen": host.screen,
                "providers": providers,
                "fragments": sorted(set(host.fragments)),
            },
        )

    @staticmethod
    def _short(name: str) -> str:

        return name.rpartition("/")[2] or name
