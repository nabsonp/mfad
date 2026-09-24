"""
Rota de serviço consumida por mais de um micro frontend.

É o acoplamento que nenhum dos outros grafos mostra. As partes não
se importam, não se navegam e não trocam mensagens — e mesmo assim
não podem evoluir separadamente, porque dependem do mesmo contrato
de backend. Uma mudança de formato na resposta quebra todas de uma
vez, e quem altera o serviço precisa saber quem são todas.

O agrupamento é pelo CAMINHO, não pelo caminho mais o método: uma
aplicação que lê e outra que escreve no mesmo recurso compartilham
o mesmo contrato, ainda que por verbos diferentes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from damfe.application.ports import Rule
from damfe.domain import AntiPatternDetection, ArtifactSet, SourceLocation


@dataclass
class Endpoint:

    path: str
    callers: dict[str, list[SourceLocation]] = field(default_factory=dict)
    methods: set[str] = field(default_factory=set)


class HammeringApis(Rule):

    name = "hammering-apis"

    description = (
        "Rota de serviço externo consumida por mais de um micro "
        "frontend, criando dependência compartilhada de contrato."
    )

    def __init__(self, min_callers: int = 2):

        #: A partir de quantos consumidores a rota é considerada
        #: compartilhada. Dois já bastam: o acoplamento existe a
        #: partir do segundo.
        self.min_callers = min_callers

    def check(self, artifacts: ArtifactSet) -> list[AntiPatternDetection]:

        endpoints = self._endpoints(artifacts)

        return [
            self._detection(endpoint)
            for endpoint in endpoints
            if len(endpoint.callers) >= self.min_callers
        ]

    @staticmethod
    def _endpoints(artifacts: ArtifactSet) -> list[Endpoint]:

        grouped: dict[str, Endpoint] = {}

        for call in artifacts.api_calls:

            endpoint = grouped.setdefault(call.path, Endpoint(path=call.path))

            endpoint.methods.add(call.method)

            endpoint.callers.setdefault(call.microfrontend, []).append(
                call.at
            )

        return [grouped[path] for path in sorted(grouped)]

    def _detection(self, endpoint: Endpoint) -> AntiPatternDetection:

        callers = sorted(endpoint.callers)

        return AntiPatternDetection(
            rule=self.name,
            dimension="backend compartilhado",
            explanation=(
                "A mesma rota é consumida por mais de um micro "
                "frontend. Uma mudança no contrato do serviço "
                "afeta todos eles ao mesmo tempo, sem que nenhum "
                "dependa diretamente do outro."
            ),
            message=(
                f"A rota {endpoint.path} é chamada por "
                f"{len(callers)} micro frontends: "
                + ", ".join(self._short(caller) for caller in callers)
            ),
            subjects=callers,
            locations=[
                location
                for caller in callers
                for location in endpoint.callers[caller]
            ],
            metadata={
                "relation": "shared_endpoint",
                # Os dois sentidos: a relação não tem direção, e o
                # desenho traça um arco para cada ordem.
                "edges": [
                    [source, target]
                    for source in callers
                    for target in callers
                    if source != target
                ],
                "path": endpoint.path,
                "methods": sorted(endpoint.methods),
                "callers": callers,
            },
        )

    @staticmethod
    def _short(name: str) -> str:

        return name.rpartition("/")[2] or name
