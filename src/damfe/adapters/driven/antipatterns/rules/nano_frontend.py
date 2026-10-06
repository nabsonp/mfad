"""
Micro frontend pequeno demais para se sustentar como unidade.

O catálogo descreve a fragmentação excessiva: a unidade é tão
pequena que o custo de tê-la separada supera o ganho.

Dois critérios em OU. O PISO é absoluto e não depende de vizinho
nenhum: abaixo dele a unidade entrega pouco demais para ser micro
frontend. O OUTLIER é a cerca inferior de Tukey sobre a distribuição
do próprio sistema, e só vale quando há distribuição para medir.
"""

from __future__ import annotations

from damfe.adapters.driven.antipatterns.alignment import (
    Sizes,
    fences,
    peers,
)
from damfe.application.ports import Rule
from damfe.domain import AntiPattern, AntiPatternDetection, MicroFrontendArchitecture


class NanoFrontend(Rule):

    anti_pattern = AntiPattern(
        name="nano-frontend",
        description=(
            "Micro frontend pequeno demais para se sustentar como "
            "unidade de implantação."
        ),
        category="Intra-frontend",
        reference="https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Nano%20Frontend",
    )

    def __init__(self, floor: int = 5):

        #: Piso absoluto de telas somadas a fragmentos.
        #:
        #: Escolha declarada, não medida. Nos dois sistemas de
        #: referência ele acusa 9 das 10 unidades, e carece de
        #: calibração contra a base do estudo.
        self.floor = floor

    def check(
        self,
        architecture: MicroFrontendArchitecture,
    ) -> list[AntiPatternDetection]:

        candidates = peers(architecture)

        sizes = Sizes.of(candidates)

        measured = {
            item.id: len(item.screens) + len(item.fragments)
            for item in candidates
            # Extração que não resolveu o entrypoint devolve zero em
            # tudo, e entraria na distribuição puxando-a para baixo
            # além de ser acusada. Falha de leitura não é anti-padrão.
            if item.metadata.get("entrypoint_resolved") is not False
        }

        limit = fences(list(measured.values()))

        found: list[AntiPatternDetection] = []

        for microfrontend in candidates:

            size = measured.get(microfrontend.id)

            if size is None:
                continue

            if size <= self.floor:
                criterion, threshold = "piso absoluto", float(self.floor)

            elif limit and size < limit.low:
                criterion, threshold = "outlier inferior", limit.low

            else:
                continue

            found.append(
                self._detection(
                    microfrontend, size, criterion, threshold, limit, sizes
                )
            )

        return found

    def _detection(
        self,
        microfrontend,
        size: int,
        criterion: str,
        threshold: float,
        limit,
        sizes,
    ) -> AntiPatternDetection:

        screens = len(microfrontend.screens)
        fragments = len(microfrontend.fragments)

        return AntiPatternDetection(
            anti_pattern=self.name,
            dimension="tamanho",
            explanation=(
                "Indício, não prova: um micro frontend pequeno é "
                "legítimo quando constitui sozinho uma capacidade "
                "inteira. O corte relativo é a cerca inferior de "
                "Tukey sobre a distribuição do próprio sistema, que "
                "não acusa ninguém quando as unidades são homogêneas."
            ),
            message=(
                f"{self._short(microfrontend.id)} tem {screens} telas "
                f"e {fragments} fragmentos, somando {size}, no máximo "
                f"{threshold:g} ({criterion})."
            ),
            subjects=[microfrontend.id],
            metadata={
                "criterio": criterion,
                "limiar": threshold,
                "telas": screens,
                "fragmentos": fragments,
                "linhas": microfrontend.size.code_lines,
                "piso": self.floor,
                "mediana_telas": sizes.screens,
                "mediana_fragmentos": sizes.fragments,
                **(
                    {"q1": limit.q1, "q3": limit.q3, "iqr": limit.iqr}
                    if limit
                    else {"distribuicao": "sem amostra suficiente"}
                ),
            },
        )

    @staticmethod
    def _short(name: str) -> str:

        return name.rpartition("/")[2] or name
