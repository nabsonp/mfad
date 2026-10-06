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

    def __init__(self, size_factor: float = 0.4, floor: int = 5):

        #: Que fração da mediana do sistema a unidade precisa estar
        #: abaixo para ser acusada.
        self.size_factor = size_factor

        #: Piso absoluto de telas somadas a fragmentos: abaixo disto
        #: a unidade é nano, qualquer que seja a mediana.
        #:
        #: Vale em OU com o relativo, não em E: basta uma das duas
        #: condições. Isso faz o piso dominar sempre que ele for mais
        #: frouxo que a mediana — o que é a intenção, porque a
        #: premissa é que abaixo dele a unidade é pequena demais para
        #: ser micro frontend, independentemente dos vizinhos.
        #:
        #: O número não vem de medida. Nos dois sistemas de
        #: referência ele acusa 9 das 10 unidades, e carece de
        #: calibração contra a base do estudo.
        self.floor = floor

    def check(
        self,
        architecture: MicroFrontendArchitecture,
    ) -> list[AntiPatternDetection]:

        candidates = peers(architecture)

        sizes = Sizes.of(candidates)

        # Sem medida não há comparação. Ver `Sizes.measurable`.
        if not sizes.measurable:
            return []

        relative = (sizes.screens + sizes.fragments) * self.size_factor

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

            # Telas e fragmentos somados, porque as duas formas de
            # entregar interface contam: uma unidade sem tela que
            # publica muitos fragmentos não é nano.
            size = screens + fragments

            if size > self.floor and size > relative:
                continue

            found.append(
                self._detection(
                    microfrontend, screens, fragments, code_lines,
                    criterion=(
                        "piso absoluto"
                        if size <= self.floor
                        else "tamanho relativo"
                    ),
                    threshold=(
                        self.floor if size <= self.floor else relative
                    ),
                    sizes=sizes,
                )
            )

        return found

    def _detection(
        self,
        microfrontend,
        screens: int,
        fragments: int,
        code_lines: int,
        criterion: str,
        threshold: float,
        sizes,
    ) -> AntiPatternDetection:

        return AntiPatternDetection(
            anti_pattern=self.name,
            dimension="tamanho",
            explanation=(
                "Indício, não prova: um micro frontend pequeno é "
                "legítimo quando constitui sozinho uma capacidade "
                "inteira. O limiar é o MENOR entre o teto absoluto e "
                "a fração da mediana do sistema — o relativo manda "
                "onde ele é mais apertado, para a regra não acusar "
                "unidade que é normal entre seus pares."
            ),
            message=(
                f"{self._short(microfrontend.id)} tem {screens} telas "
                f"e {fragments} fragmentos, somando "
                f"{screens + fragments}, no máximo {threshold:g} "
                f"({criterion}; mediana do sistema: "
                f"{sizes.screens:g} telas, {sizes.fragments:g} "
                f"fragmentos)."
            ),
            subjects=[microfrontend.id],
            metadata={
                "criterio": criterion,
                "limiar": threshold,
                "telas": screens,
                "fragmentos": fragments,
                "linhas": code_lines,
                "mediana_telas": sizes.screens,
                "mediana_fragmentos": sizes.fragments,
                "fator": self.size_factor,
                "teto": self.floor,
            },
        )

    @staticmethod
    def _short(name: str) -> str:

        return name.rpartition("/")[2] or name
