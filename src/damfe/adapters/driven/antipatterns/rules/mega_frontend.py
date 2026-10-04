"""
Micro frontend que serve mais de um domínio de negócio.

O catálogo descreve "múltiplas responsabilidades que deveriam
estar separadas". A operacionalização é o desalinhamento entre as
duas decomposições: as telas do micro frontend caem em domínios
diferentes.

A saída nomeia **quais telas destoam e para onde iriam**, em vez de
dizer que ele serve N domínios. Uma contagem não diz o que fazer;
um nome de tela e um destino, sim.

Sem mapa de domínios a regra cai no tamanho relativo — proxy mais
fraco, porque um micro frontend grande e coeso não é Mega Frontend.
O modo usado vai declarado na saída.
"""

from __future__ import annotations

from damfe.adapters.driven.antipatterns.alignment import (
    Sizes,
    alignments,
    peers,
)
from damfe.application.ports import Rule
from damfe.domain import AntiPatternDetection, MicroFrontendArchitecture


class MegaFrontend(Rule):

    name = "mega-frontend"

    description = (
        "Micro frontend que serve mais de um domínio de negócio, "
        "concentrando responsabilidades que deveriam estar separadas."
    )

    def __init__(self, size_factor: float = 2.0):

        #: Quantas vezes acima da mediana do sistema um micro
        #: frontend precisa estar para ser acusado no modo sem mapa.
        self.size_factor = size_factor

    def check(self, architecture: MicroFrontendArchitecture) -> list[AntiPatternDetection]:

        if architecture.domains:
            return self._by_domain(architecture)

        return self._by_size(architecture)

    # ------------------------------------------------------------------

    def _by_domain(self, architecture: MicroFrontendArchitecture) -> list[AntiPatternDetection]:

        spread = alignments(architecture)

        by_screen = {
            screen: domain.name
            for domain in architecture.domains
            for screen in domain.screens
        }

        found: list[AntiPatternDetection] = []

        for microfrontend in peers(architecture):

            entry = spread[microfrontend.id]

            if not entry.determined or not entry.outliers:
                continue

            estranhas = [
                (screen.component, by_screen[screen.id])
                for screen in microfrontend.screens
                if by_screen.get(screen.id) in entry.outliers
            ]

            found.append(
                AntiPatternDetection(
                    rule=self.name,
                    dimension="domínio",
                    explanation=(
                        "As telas deste micro frontend pertencem a "
                        "domínios de negócio diferentes. Cada domínio "
                        "evolui por razões próprias, e mantê-los na "
                        "mesma unidade acopla mudanças que não têm "
                        "relação entre si."
                    ),
                    message=(
                        f"{self._short(microfrontend.id)} serve "
                        f"{len(entry.screens)} domínios. Predomina "
                        f"{entry.dominant} com "
                        f"{entry.screens[entry.dominant]} telas; "
                        + "; ".join(
                            f"{tela} pertence a {dominio}"
                            for tela, dominio in estranhas
                        )
                    ),
                    subjects=[microfrontend.id],
                    metadata={
                        "criterio": "mapa de domínios",
                        "dominante": entry.dominant,
                        "dominios": entry.screens,
                        "telas_destoantes": [
                            {"tela": tela, "dominio": dominio}
                            for tela, dominio in estranhas
                        ],
                        "telas_sem_dominio": entry.unassigned,
                    },
                )
            )

        return found

    def _by_size(self, architecture: MicroFrontendArchitecture) -> list[AntiPatternDetection]:

        candidates = peers(architecture)

        sizes = Sizes.of(candidates)

        # Sem medida não há comparação. Ver `Sizes.measurable`.
        if not sizes.measurable:
            return []

        found: list[AntiPatternDetection] = []

        for microfrontend in candidates:

            telas = len(microfrontend.screens)
            linhas = microfrontend.size.code_lines

            if (
                telas < sizes.screens * self.size_factor
                or linhas < sizes.code_lines * self.size_factor
            ):
                continue

            found.append(
                AntiPatternDetection(
                    rule=self.name,
                    dimension="tamanho",
                    explanation=(
                        "Sem mapa de domínios, a regra usa o tamanho "
                        "relativo como indício. É proxy mais fraco: "
                        "um micro frontend grande e coeso não é Mega "
                        "Frontend. Declare os domínios em "
                        ".damfe/domains.yml para uma detecção melhor "
                        "fundamentada."
                    ),
                    message=(
                        f"{self._short(microfrontend.id)} tem {telas} "
                        f"telas e {linhas} linhas, acima de "
                        f"{self.size_factor}× a mediana do sistema "
                        f"({sizes.screens:g} telas, "
                        f"{sizes.code_lines:g} linhas)."
                    ),
                    subjects=[microfrontend.id],
                    metadata={
                        "criterio": "tamanho relativo",
                        "telas": telas,
                        "linhas": linhas,
                        "mediana_telas": sizes.screens,
                        "mediana_linhas": sizes.code_lines,
                    },
                )
            )

        return found

    @staticmethod
    def _short(name: str) -> str:

        return name.rpartition("/")[2] or name
