"""
Micro frontend que é pedaço de um domínio, não uma unidade dele.

O catálogo descreve "poucas telas ou fragmentos" e atribui a causa
a confundir micro frontend com componente de interface. O problema
não é ser pequeno: é **não ser uma unidade de domínio**. Um micro
frontend com uma tela só é legítimo quando aquela tela é o domínio.

Por isso o critério é o desalinhamento: todas as telas num domínio
que outro micro frontend também serve, e serve mais. O tamanho não
é condição — é o que **desambigua a direção**, dizendo qual dos
dois é o pedaço e qual é o dono. Divisão equilibrada não é Nano
Frontend; é um domínio mal repartido, que é outro achado.

Sem mapa de domínios a regra cai no tamanho relativo, declarando
que o fez.
"""

from __future__ import annotations

from damfe.adapters.driven.antipatterns.alignment import (
    Sizes,
    alignments,
    peers,
)
from damfe.application.ports import Rule
from damfe.domain import AntiPatternDetection, ArtifactSet


class NanoFrontend(Rule):

    name = "nano-frontend"

    description = (
        "Micro frontend que cobre parte de um domínio servido por "
        "outro, em vez de constituir uma unidade de domínio."
    )

    def __init__(self, size_factor: float = 0.4, dominance: float = 2.0):

        #: Fração da mediana abaixo da qual um micro frontend é
        #: acusado no modo sem mapa.
        self.size_factor = size_factor

        #: Quantas vezes mais telas o dono precisa ter no domínio
        #: para que o outro seja considerado pedaço, e não metade.
        self.dominance = dominance

    def check(self, artifacts: ArtifactSet) -> list[AntiPatternDetection]:

        if artifacts.domains:
            return self._by_domain(artifacts)

        return self._by_size(artifacts)

    # ------------------------------------------------------------------

    def _by_domain(self, artifacts: ArtifactSet) -> list[AntiPatternDetection]:

        spread = alignments(artifacts)

        found: list[AntiPatternDetection] = []

        for microfrontend in peers(artifacts):

            entry = spread[microfrontend.id]

            # Serve mais de um domínio, ou nenhum determinável:
            # nos dois casos esta regra não tem o que dizer.
            if not entry.determined or len(entry.screens) != 1:
                continue

            domain = entry.dominant

            mine = entry.screens[domain]

            owner, theirs = self._owner(spread, domain, microfrontend.id)

            if not owner or theirs < mine * self.dominance:
                continue

            found.append(
                AntiPatternDetection(
                    rule=self.name,
                    dimension="domínio",
                    explanation=(
                        "Este micro frontend cobre parte de um domínio "
                        "que outro já serve, e em menor extensão. Não "
                        "é uma unidade de domínio, é um recorte dele — "
                        "e o custo de mantê-lo separado não é pago por "
                        "uma fronteira de negócio."
                    ),
                    message=(
                        f"{self._short(microfrontend.id)} serve "
                        f"{mine} de {mine + theirs} telas do domínio "
                        f"{domain}; {self._short(owner)} serve as "
                        f"outras {theirs}."
                    ),
                    subjects=[microfrontend.id, owner],
                    metadata={
                        "criterio": "mapa de domínios",
                        "dominio": domain,
                        "telas_proprias": mine,
                        "dono": owner,
                        "telas_do_dono": theirs,
                        "tamanho": {
                            "telas": len(microfrontend.screens),
                            "fragmentos": len(microfrontend.fragments),
                            "linhas": microfrontend.size.code_lines,
                        },
                    },
                )
            )

        return found

    @staticmethod
    def _owner(spread: dict, domain: str, exclude: str):
        """Quem mais serve este domínio, além do acusado."""

        best, count = None, 0

        for identifier, entry in spread.items():

            if identifier == exclude:
                continue

            serves = entry.screens.get(domain, 0)

            if serves > count:
                best, count = identifier, serves

        return best, count

    def _by_size(self, artifacts: ArtifactSet) -> list[AntiPatternDetection]:

        candidates = peers(artifacts)

        sizes = Sizes.of(candidates)

        # Sem medida não há comparação. Ver `Sizes.measurable`.
        if not sizes.measurable:
            return []

        found: list[AntiPatternDetection] = []

        for microfrontend in candidates:

            telas = len(microfrontend.screens)
            fragmentos = len(microfrontend.fragments)
            linhas = microfrontend.size.code_lines

            if telas + fragmentos > (
                sizes.screens + sizes.fragments
            ) * self.size_factor:
                continue

            found.append(
                AntiPatternDetection(
                    rule=self.name,
                    dimension="tamanho",
                    explanation=(
                        "Sem mapa de domínios, a regra usa o tamanho "
                        "relativo como indício. É proxy mais fraco: um "
                        "micro frontend pequeno é legítimo quando "
                        "constitui um domínio inteiro. Declare os "
                        "domínios em .damfe/domains.yml para uma "
                        "detecção melhor fundamentada."
                    ),
                    message=(
                        f"{self._short(microfrontend.id)} tem {telas} "
                        f"telas e {fragmentos} fragmentos, abaixo de "
                        f"{self.size_factor:g}× a mediana do sistema "
                        f"({sizes.screens:g} telas, "
                        f"{sizes.fragments:g} fragmentos)."
                    ),
                    subjects=[microfrontend.id],
                    metadata={
                        "criterio": "tamanho relativo",
                        "telas": telas,
                        "fragmentos": fragmentos,
                        "linhas": linhas,
                        "mediana_telas": sizes.screens,
                        "mediana_fragmentos": sizes.fragments,
                    },
                )
            )

        return found

    @staticmethod
    def _short(name: str) -> str:

        return name.rpartition("/")[2] or name
