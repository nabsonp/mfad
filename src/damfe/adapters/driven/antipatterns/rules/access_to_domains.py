"""
Micro frontend que consome serviços de vários domínios.

Distinto do Mega Frontend, e a diferença importa: o Mega olha o que
o micro frontend **serve** — suas telas; este olha de que ele
**depende** — suas chamadas. Um micro frontend pode servir um
domínio só e consumir três, e aí o problema é de federação de API,
com remédio diferente.

Depende do mapa de domínios. Sem ele não há critério: domínio de
negócio não está no código, e qualquer aproximação por prefixo de
caminho seria arbitrária.
"""

from __future__ import annotations

from damfe.adapters.driven.antipatterns.alignment import alignments, peers
from damfe.application.ports import Rule
from damfe.domain import AntiPatternDetection, MicroFrontendArchitecture


class AccessToDifferentDomains(Rule):

    name = "access-to-different-domains"

    description = (
        "Micro frontend que chama serviços de mais de um domínio de "
        "negócio, acoplando-se diretamente a cada um deles."
    )

    def __init__(self, min_domains: int = 2):

        #: A partir de quantos domínios consumidos o acoplamento é
        #: acusado.
        self.min_domains = min_domains

    def check(self, architecture: MicroFrontendArchitecture) -> list[AntiPatternDetection]:

        if not architecture.domains:
            return []

        spread = alignments(architecture)

        by_path = {
            path: domain.name
            for domain in architecture.domains
            for path in domain.api_calls
        }

        found: list[AntiPatternDetection] = []

        for microfrontend in peers(architecture):

            called = spread[microfrontend.id].called

            if len(called) < self.min_domains:
                continue

            endpoints = sorted(
                {
                    f"{call.method} {call.path}"
                    for call in architecture.api_calls
                    if call.microfrontend == microfrontend.id
                    and by_path.get(call.path) in called
                }
            )

            found.append(
                AntiPatternDetection(
                    rule=self.name,
                    dimension="domínio",
                    explanation=(
                        "O micro frontend chama diretamente serviços "
                        "de domínios diferentes. Cada contrato passa a "
                        "ser dependência dele, e depreciar qualquer um "
                        "exige coordenar com todos os consumidores."
                    ),
                    message=(
                        f"{self._short(microfrontend.id)} consome "
                        f"serviços de {len(called)} domínios: "
                        + ", ".join(sorted(called))
                    ),
                    subjects=[microfrontend.id],
                    locations=[
                        call.at
                        for call in architecture.api_calls
                        if call.microfrontend == microfrontend.id
                        and by_path.get(call.path) in called
                    ],
                    metadata={
                        "criterio": "mapa de domínios",
                        "dominios": sorted(called),
                        "endpoints": endpoints,
                    },
                )
            )

        return found

    @staticmethod
    def _short(name: str) -> str:

        return name.rpartition("/")[2] or name
