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
from damfe.domain import (
    AntiPattern,
    AntiPatternDetection,
    Endpoint,
    MicroFrontendArchitecture,
    SourceLocation,
)


class HammeringApis(Rule):

    anti_pattern = AntiPattern(
        name="hammering-apis",
        description=(
            "Rota de serviço externo consumida por mais de um micro "
            "frontend, criando dependência compartilhada de contrato."
        ),
        category="Inter-frontend",
        reference="https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Hammering%20APIs",
    )

    def __init__(self, min_callers: int = 2):

        #: A partir de quantos consumidores a rota é considerada
        #: compartilhada. Dois já bastam: o acoplamento existe a
        #: partir do segundo.
        self.min_callers = min_callers

    def check(self, architecture: MicroFrontendArchitecture) -> list[AntiPatternDetection]:

        return [
            self._detection(endpoint, architecture)
            for endpoint in architecture.endpoints
            if len(endpoint.microfrontends) >= self.min_callers
        ]

    def _detection(
        self,
        endpoint: Endpoint,
        architecture: MicroFrontendArchitecture,
    ) -> AntiPatternDetection:

        callers = sorted(endpoint.microfrontends)

        return AntiPatternDetection(
            anti_pattern=self.name,
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
            # As localizações vêm das chamadas, não do endpoint:
            # ele é o nó externo, e quem registra onde a chamada
            # acontece é o `ApiCall`.
            locations=[
                call.at
                for call in architecture.api_calls
                if call.path == endpoint.path
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
