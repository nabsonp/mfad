"""
Micro frontend pequeno demais para se sustentar como unidade.

O catálogo descreve a fragmentação excessiva: a unidade é tão
pequena que o custo de tê-la separada supera o ganho.

Dois critérios em OU. O PISO é absoluto e não depende de vizinho
nenhum: abaixo dele a unidade entrega pouco demais para ser micro
frontend. O OUTLIER é a cerca inferior de Tukey sobre a distribuição
do próprio sistema, e só vale quando há distribuição para medir.

Os dois exigem também CÓDIGO abaixo da mediana do sistema. Telas e
fragmentos contam por onde a unidade é vista, não quanto ela faz: uma
aplicação Angular com duas rotas e dezenas de abas e diálogos tem
poucas telas e é das maiores do sistema. É a mesma exigência dupla do
`mega-frontend`, do lado oposto — pouca tela com muito código não é
unidade pequena, é tela densa.
"""

from __future__ import annotations

import statistics

from mfad.adapters.driven import i18n
from mfad.adapters.driven.antipatterns.alignment import (
    Sizes,
    fences,
    peers,
)
from mfad.application.ports import Rule
from mfad.domain import AntiPattern, AntiPatternDetection, MicroFrontendArchitecture


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

        lines = sorted(
            item.size.code_lines
            for item in candidates
            if item.id in measured
        )

        median_lines = statistics.median(lines) if lines else 0

        found: list[AntiPatternDetection] = []

        for microfrontend in candidates:

            size = measured.get(microfrontend.id)

            if size is None:
                continue

            # Mais código que a metade dos pares não é unidade pequena.
            if microfrontend.size.code_lines >= median_lines:
                continue

            if size <= self.floor:
                criterion, threshold = "nano.criterion.floor", float(self.floor)

            elif limit and size < limit.low:
                criterion, threshold = "nano.criterion.outlier", limit.low

            else:
                continue

            found.append(
                self._detection(
                    microfrontend, size, criterion, threshold, limit, sizes,
                    median_lines,
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
        median_lines: float,
    ) -> AntiPatternDetection:

        screens = len(microfrontend.screens)
        fragments = len(microfrontend.fragments)

        text = {
            "dimension": i18n.ref("dimension.size"),
            "explanation": i18n.ref("nano.explanation"),
            "message": i18n.ref(
                "nano.message",
                name=self._short(microfrontend.id),
                screens=screens,
                fragments=fragments,
                size=size,
                threshold=f"{threshold:g}",
                criterion=i18n.ref(criterion),
                lines=microfrontend.size.code_lines,
                median=f"{median_lines:g}",
            ),
        }

        text["facts"] = [
            i18n.fact("fact.screens", screens),
            i18n.fact("fact.fragments", fragments),
            i18n.fact("fact.size", size),
            i18n.fact("fact.size_limit", i18n.ref("fact.limit_by", value=f"{threshold:g}", criterion=i18n.ref(criterion))),
            i18n.fact("fact.code_lines", microfrontend.size.code_lines),
            i18n.fact("fact.median_lines", f"{median_lines:g}"),
        ]

        return AntiPatternDetection(
            anti_pattern=self.name,
            dimension=i18n.t(text["dimension"]),
            explanation=i18n.t(text["explanation"]),
            message=i18n.t(text["message"]),
            subjects=[microfrontend.id],
            metadata={
                "text": text,
                "criterio": i18n.t(criterion),
                "limiar": threshold,
                "telas": screens,
                "fragmentos": fragments,
                "linhas": microfrontend.size.code_lines,
                "piso": self.floor,
                "mediana_telas": sizes.screens,
                "mediana_fragmentos": sizes.fragments,
                "mediana_linhas": median_lines,
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
