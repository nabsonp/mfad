"""
Micro frontend pequeno demais perto dos seus pares.

O catálogo descreve a fragmentação excessiva: a unidade é tão
pequena que não se sustenta como unidade de implantação, e o custo
de tê-la separada supera o ganho.

A medida é relativa, em telas e fragmentos. Um micro frontend
pequeno pode ser perfeitamente legítimo — é o caso de um que
constitui sozinho uma capacidade inteira —, então isto é indício e
não veredito, e a saída diz contra o que a unidade foi comparada.
"""

from __future__ import annotations

from damfe.adapters.driven.antipatterns.alignment import Sizes, peers
from damfe.application.ports import Rule
from damfe.domain import AntiPatternDetection, MicroFrontendArchitecture


class NanoFrontend(Rule):

    name = "nano-frontend"

    description = (
        "Micro frontend pequeno demais para se sustentar como "
        "unidade de implantação."
    )

    def __init__(self, size_factor: float = 0.4):

        #: Que fração da mediana do sistema a unidade precisa estar
        #: abaixo para ser acusada.
        self.size_factor = size_factor

    def check(
        self,
        architecture: MicroFrontendArchitecture,
    ) -> list[AntiPatternDetection]:

        candidates = peers(architecture)

        sizes = Sizes.of(candidates)

        # Sem medida não há comparação. Ver `Sizes.measurable`.
        if not sizes.measurable:
            return []

        found: list[AntiPatternDetection] = []

        for microfrontend in candidates:

            screens = len(microfrontend.screens)
            fragments = len(microfrontend.fragments)
            code_lines = microfrontend.size.code_lines

            # Telas e fragmentos somados, porque as duas formas de
            # entregar interface contam: uma unidade sem tela que
            # publica cinco fragmentos não é nano.
            if screens + fragments > (
                sizes.screens + sizes.fragments
            ) * self.size_factor:
                continue

            found.append(
                AntiPatternDetection(
                    rule=self.name,
                    dimension="tamanho",
                    explanation=(
                        "Tamanho relativo é indício, não prova: um "
                        "micro frontend pequeno é legítimo quando "
                        "constitui sozinho uma capacidade inteira. A "
                        "comparação é contra a mediana do próprio "
                        "sistema, e vai na saída para quem lê poder "
                        "discordar."
                    ),
                    message=(
                        f"{self._short(microfrontend.id)} tem "
                        f"{screens} telas e {fragments} fragmentos, "
                        f"abaixo de {self.size_factor:g}× a mediana "
                        f"do sistema ({sizes.screens:g} telas, "
                        f"{sizes.fragments:g} fragmentos)."
                    ),
                    subjects=[microfrontend.id],
                    metadata={
                        "telas": screens,
                        "fragmentos": fragments,
                        "linhas": code_lines,
                        "mediana_telas": sizes.screens,
                        "mediana_fragmentos": sizes.fragments,
                        "fator": self.size_factor,
                    },
                )
            )

        return found

    @staticmethod
    def _short(name: str) -> str:

        return name.rpartition("/")[2] or name
