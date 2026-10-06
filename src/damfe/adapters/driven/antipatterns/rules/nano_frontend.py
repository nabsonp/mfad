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

    def __init__(self, size_factor: float = 0.4, floor: int = 3):

        #: Que fração da mediana do sistema a unidade precisa estar
        #: abaixo para ser acusada.
        self.size_factor = size_factor

        #: Piso absoluto: unidade sem tela nenhuma que publique no
        #: máximo esta quantidade de fragmentos é nano, qualquer que
        #: seja a mediana.
        #:
        #: Existe porque a comparação relativa é cega em sistema
        #: uniforme — se toda unidade tem uma tela e um fragmento, a
        #: mediana acompanha e ninguém é acusado, por construção.
        self.floor = floor

    def check(
        self,
        architecture: MicroFrontendArchitecture,
    ) -> list[AntiPatternDetection]:

        candidates = peers(architecture)

        sizes = Sizes.of(candidates)

        found: list[AntiPatternDetection] = []

        for microfrontend in candidates:

            screens = len(microfrontend.screens)
            fragments = len(microfrontend.fragments)
            code_lines = microfrontend.size.code_lines

            # Extração que não resolveu o entrypoint devolve zero em
            # tudo. Acusar isso seria chamar falha de leitura de
            # anti-padrão.
            if microfrontend.metadata.get("entrypoint_resolved") is False:
                continue

            if self._below_floor(screens, fragments):

                found.append(
                    self._detection(
                        microfrontend, screens, fragments, code_lines,
                        criterion="piso absoluto",
                        explanation=(
                            "Sem tela nenhuma e publicando no máximo "
                            f"{self.floor} fragmentos, a unidade não "
                            "responde por URL alguma e entrega pouco "
                            "mais que um componente. O piso não depende "
                            "da mediana: num sistema em que todas as "
                            "unidades são pequenas, a comparação "
                            "relativa não acusaria ninguém."
                        ),
                        message=(
                            f"{self._short(microfrontend.id)} não tem "
                            f"tela alguma e publica {fragments} "
                            f"fragmentos."
                        ),
                        sizes=sizes,
                    )
                )
                continue

            # Sem medida não há comparação. Ver `Sizes.measurable`.
            if not sizes.measurable:
                continue

            # Telas e fragmentos somados, porque as duas formas de
            # entregar interface contam: uma unidade sem tela que
            # publica cinco fragmentos não é nano.
            if screens + fragments > (
                sizes.screens + sizes.fragments
            ) * self.size_factor:
                continue

            found.append(
                self._detection(
                    microfrontend, screens, fragments, code_lines,
                    criterion="tamanho relativo",
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
                    sizes=sizes,
                )
            )

        return found

    def _below_floor(self, screens: int, fragments: int) -> bool:
        """Sem tela alguma e publicando pouco."""

        return screens == 0 and fragments <= self.floor

    def _detection(
        self,
        microfrontend,
        screens: int,
        fragments: int,
        code_lines: int,
        criterion: str,
        explanation: str,
        message: str,
        sizes,
    ) -> AntiPatternDetection:

        return AntiPatternDetection(
            anti_pattern=self.name,
            dimension="tamanho",
            explanation=explanation,
            message=message,
            subjects=[microfrontend.id],
            metadata={
                "criterio": criterion,
                "telas": screens,
                "fragmentos": fragments,
                "linhas": code_lines,
                "mediana_telas": sizes.screens,
                "mediana_fragmentos": sizes.fragments,
                "fator": self.size_factor,
                "piso": self.floor,
            },
        )

    @staticmethod
    def _short(name: str) -> str:

        return name.rpartition("/")[2] or name
