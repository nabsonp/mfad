"""
Micro frontend grande demais perto dos seus pares.

O catálogo descreve "múltiplas responsabilidades que deveriam
estar separadas". Sem mapa de domínios não há como afirmar QUAIS
responsabilidades são, então a v0 mede a consequência observável:
uma unidade que concentra telas, fragmentos e código muito acima
da mediana do sistema.

É indício, não prova. Um micro frontend grande e coeso não é um
Mega Frontend, e a regra não tem como distinguir os dois — por
isso a saída diz contra o que a unidade foi comparada, para quem
lê poder discordar.
"""

from __future__ import annotations

from damfe.adapters.driven.antipatterns.alignment import Sizes, peers
from damfe.application.ports import Rule
from damfe.domain import AntiPattern, AntiPatternDetection, MicroFrontendArchitecture


class MegaFrontend(Rule):

    anti_pattern = AntiPattern(
        name="mega-frontend",
        description=(
            "Micro frontend muito maior que seus pares, concentrando "
            "responsabilidades que deveriam estar separadas."
        ),
        category="Intra-frontend",
        reference="https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Mega%20Frontend",
    )

    def __init__(self, size_factor: float = 2.0):

        #: Quantas vezes acima da mediana do sistema a unidade
        #: precisa estar para ser acusada.
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

            # As três medidas juntas, não qualquer uma delas. Uma
            # unidade com muitas telas e pouco código é um menu; uma
            # com muito código e uma tela é uma biblioteca. Mega
            # Frontend é a que cresce nas três ao mesmo tempo.
            if (
                screens < sizes.screens * self.size_factor
                or code_lines < sizes.code_lines * self.size_factor
            ):
                continue

            found.append(
                AntiPatternDetection(
                    anti_pattern=self.name,
                    dimension="tamanho",
                    explanation=(
                        "Tamanho relativo é indício, não prova: um "
                        "micro frontend grande e coeso não é Mega "
                        "Frontend. A comparação é contra a mediana "
                        "do próprio sistema, e vai na saída para "
                        "quem lê poder discordar."
                    ),
                    message=(
                        f"{self._short(microfrontend.id)} tem "
                        f"{screens} telas, {fragments} fragmentos e "
                        f"{code_lines} linhas, acima de "
                        f"{self.size_factor}× a mediana do sistema "
                        f"({sizes.screens:g} telas, "
                        f"{sizes.code_lines:g} linhas)."
                    ),
                    subjects=[microfrontend.id],
                    metadata={
                        "telas": screens,
                        "fragmentos": fragments,
                        "linhas": code_lines,
                        "mediana_telas": sizes.screens,
                        "mediana_fragmentos": sizes.fragments,
                        "mediana_linhas": sizes.code_lines,
                        "fator": self.size_factor,
                    },
                )
            )

        return found

    @staticmethod
    def _short(name: str) -> str:

        return name.rpartition("/")[2] or name
