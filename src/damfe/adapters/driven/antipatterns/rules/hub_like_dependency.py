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
from damfe.domain import AntiPattern, AntiPatternDetection, MicroFrontendArchitecture, SourceLocation


@dataclass
class Host:
    """O que uma tela hospeda de fora."""

    screen: str
    owner: str
    providers: set[str] = field(default_factory=set)
    fragments: list[str] = field(default_factory=list)
    locations: list[SourceLocation] = field(default_factory=list)


class HubLikeDependency(Rule):

    anti_pattern = AntiPattern(
        name="hub-like-dependency",
        description=(
            "Tela que instancia muitos fragmentos, concentrando "
            "dependências num só ponto."
        ),
        category="Inter-frontend",
        reference="https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Hub-like%20Dependency",
    )

    def __init__(self, min_fragments: int = 5):

        #: A partir de quantos fragmentos a tela é considerada um
        #: hub.
        #:
        #: A contagem é de FRAGMENTOS, não de micro frontends
        #: provedores. É a quantidade de peças que a tela precisa
        #: montar que a torna um ponto de convergência — cinco
        #: fragmentos de um provedor só concentram tanta mudança de
        #: contrato quanto cinco de cinco.
        #:
        #: Contar provedores distintos, como se fazia, punia o
        #: desenho normal: numa arquitetura com biblioteca de
        #: componentes compartilhada, qualquer tela que use um
        #: componente dela mais um fragmento qualquer já somava dois
        #: provedores e virava hub.
        self.min_fragments = min_fragments

    def check(self, architecture: MicroFrontendArchitecture) -> list[AntiPatternDetection]:

        hosts = self._hosts(architecture)

        return [
            self._detection(host)
            for host in hosts.values()
            if len(host.fragments) >= self.min_fragments
        ]

    def _hosts(self, architecture: MicroFrontendArchitecture) -> dict[str, Host]:
        """
        Agrupa os fragmentos instanciados por tela.

        A ligação vem do próprio sítio de renderização, que já sabe em
        que telas aparece. Antes era pelo ARQUIVO — a tela cujo
        arquivo instancia o fragmento —, e isso quebrava quando várias
        telas são declaradas no mesmo roteador: o mapa ficava com uma
        tela arbitrária por arquivo, e a acusação caía sobre ela.
        """

        screens = {
            screen.id: screen
            for microfrontend in architecture.microfrontends
            for screen in microfrontend.screens
        }

        hosts: dict[str, Host] = {}

        for item in architecture.fragment_imports:

            for render in item.renders:

                for identifier in render.screens:

                    screen = screens.get(identifier)

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
            anti_pattern=self.name,
            dimension="composição",
            explanation=(
                "A tela instancia muitos fragmentos, concentrando "
                "num só ponto as falhas e as mudanças de contrato "
                "de todos eles."
            ),
            message=(
                f"A tela {host.screen}, de {self._short(host.owner)}, "
                f"instancia {len(host.fragments)} fragmentos, de "
                f"{len(providers)} micro "
                f"{'frontend' if len(providers) == 1 else 'frontends'}: "
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
