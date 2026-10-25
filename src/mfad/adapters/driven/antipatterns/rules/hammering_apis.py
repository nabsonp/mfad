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

from mfad.adapters.driven import i18n
from mfad.application.ports import Rule
from mfad.domain import (
    AntiPattern,
    AntiPatternDetection,
    Endpoint,
    MicroFrontendArchitecture,
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

        text = {
            "dimension": i18n.ref("dimension.shared_backend"),
            "explanation": i18n.ref("hammering.explanation"),
            "message": i18n.ref(
                "hammering.message",
                path=endpoint.path,
                n=len(callers),
                names=", ".join(self._short(caller) for caller in callers),
            ),
        }

        text["facts"] = [
            i18n.fact("fact.route", endpoint.path),
            i18n.fact("fact.callers", ", ".join(self._short(caller) for caller in callers)),
        ]

        return AntiPatternDetection(
            anti_pattern=self.name,
            dimension=i18n.t(text["dimension"]),
            explanation=i18n.t(text["explanation"]),
            message=i18n.t(text["message"]),
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
                "text": text,
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
