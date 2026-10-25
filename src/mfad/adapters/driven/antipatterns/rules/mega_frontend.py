"""
Micro frontend grande demais perto dos seus pares.

O catálogo descreve "múltiplas responsabilidades que deveriam estar
separadas". Sem mapa de domínios não há como afirmar QUAIS são,
então o que se mede é a consequência observável: a unidade cresceu
muito além da distribuição do sistema.

O corte é a cerca superior de Tukey, em telas E em linhas de código.
As duas juntas, não qualquer uma: muitas telas com pouco código é um
menu, muito código com uma tela é uma biblioteca.
"""

from __future__ import annotations

from mfad.adapters.driven import i18n
from mfad.adapters.driven.antipatterns.alignment import (
    Sizes,
    fences,
    peers,
)
from mfad.application.ports import Rule
from mfad.domain import AntiPattern, AntiPatternDetection, MicroFrontendArchitecture


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

    def check(
        self,
        architecture: MicroFrontendArchitecture,
    ) -> list[AntiPatternDetection]:

        candidates = [
            item
            for item in peers(architecture)
            if item.metadata.get("entrypoint_resolved") is not False
        ]

        sizes = Sizes.of(candidates)

        by_screens = fences([len(item.screens) for item in candidates])
        by_lines = fences([item.size.code_lines for item in candidates])

        # Amostra pequena demais para falar de distribuição.
        if not by_screens or not by_lines:
            return []

        found: list[AntiPatternDetection] = []

        for microfrontend in candidates:

            screens = len(microfrontend.screens)
            code_lines = microfrontend.size.code_lines

            if screens <= by_screens.high or code_lines <= by_lines.high:
                continue

            text = {
                "dimension": i18n.ref("dimension.size"),
                "explanation": i18n.ref("mega.explanation"),
                "message": i18n.ref(
                    "mega.message",
                    name=self._short(microfrontend.id),
                    screens=screens,
                    lines=code_lines,
                    screen_fence=f"{by_screens.high:g}",
                    line_fence=f"{by_lines.high:g}",
                ),
            }

            text["facts"] = [
                i18n.fact("fact.screens", screens),
                i18n.fact("fact.screen_fence", f"{by_screens.high:g}"),
                i18n.fact("fact.code_lines", code_lines),
                i18n.fact("fact.line_fence", f"{by_lines.high:g}"),
            ]

            found.append(
                AntiPatternDetection(
                    anti_pattern=self.name,
                    dimension=i18n.t(text["dimension"]),
                    explanation=i18n.t(text["explanation"]),
                    message=i18n.t(text["message"]),
                    subjects=[microfrontend.id],
                    metadata={
                        "text": text,
                        "criterio": "outlier superior",
                        "telas": screens,
                        "fragmentos": len(microfrontend.fragments),
                        "linhas": code_lines,
                        "cerca_telas": by_screens.high,
                        "cerca_linhas": by_lines.high,
                        "mediana_telas": sizes.screens,
                        "mediana_linhas": sizes.code_lines,
                    },
                )
            )

        return found

    @staticmethod
    def _short(name: str) -> str:

        return name.rpartition("/")[2] or name
