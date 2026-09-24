"""
O cruzamento entre as duas decomposições.

O sistema está dividido de duas formas ao mesmo tempo: em micro
frontends, que é como o código foi organizado, e em domínios de
negócio, que é como o problema se organiza. As regras de
granularidade medem a distância entre as duas.

Compartilhado por `nano-frontend`, `mega-frontend` e
`access-to-different-domains`, que olham o mesmo cruzamento de
ângulos diferentes: quem serve menos de um domínio, quem serve
mais de um, e quem depende de mais de um.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from damfe.domain import ArtifactSet, MicroFrontend


@dataclass
class Alignment:
    """Como um micro frontend se distribui pelos domínios."""

    microfrontend: str

    #: domínio -> quantas telas dele o micro frontend serve
    screens: dict[str, int] = field(default_factory=dict)

    #: telas cuja rota não caiu em domínio nenhum
    unassigned: int = 0

    #: domínios dos quais ele consome serviço
    called: set[str] = field(default_factory=set)

    @property
    def domains(self) -> list[str]:
        """Do mais servido ao menos servido."""

        return sorted(self.screens, key=lambda d: -self.screens[d])

    @property
    def dominant(self) -> str | None:
        return self.domains[0] if self.screens else None

    @property
    def outliers(self) -> list[str]:
        """Domínios que ele serve além do dominante."""

        return self.domains[1:]

    @property
    def determined(self) -> bool:
        """
        Há base para julgar.

        Um micro frontend cujas telas são todas não atribuídas não
        serve "um" nem "vários" domínios — é indeterminado, e a
        regra deve se abster em vez de acusar.
        """

        return bool(self.screens)


def alignments(artifacts: ArtifactSet) -> dict[str, Alignment]:

    by_screen = {
        screen: domain.name
        for domain in artifacts.domains
        for screen in domain.screens
    }

    by_path = {
        path: domain.name
        for domain in artifacts.domains
        for path in domain.api_calls
    }

    found: dict[str, Alignment] = {}

    for microfrontend in artifacts.microfrontends:

        entry = Alignment(microfrontend=microfrontend.id)

        for screen in microfrontend.screens:

            domain = by_screen.get(screen.id)

            if domain:
                entry.screens[domain] = entry.screens.get(domain, 0) + 1
            else:
                entry.unassigned += 1

        found[microfrontend.id] = entry

    for call in artifacts.api_calls:

        domain = by_path.get(call.path)

        if domain and call.microfrontend in found:
            found[call.microfrontend].called.add(domain)

    return found


@dataclass
class Sizes:
    """
    Medianas do sistema, para o modo sem mapa de domínios.

    Relativas de propósito: "poucas telas" depende do tamanho dos
    vizinhos, e um limiar absoluto seria um número escolhido sem
    justificativa.
    """

    screens: float
    fragments: float
    code_lines: float

    @property
    def measurable(self) -> bool:
        """
        Se há medida para comparar contra.

        Mediana zero não significa "todo mundo é pequeno": significa
        que não se mediu nada. Comparar contra ela torna qualquer
        fração verdadeira — `0 < 0.4 × 0` — e a regra acusa todos os
        micro frontends de uma vez, que é exatamente o resultado que
        uma extração vazia produz.

        Quando a reconstrução não encontra telas nem fragmentos, o
        certo é a regra se abster e o relatório dizer que faltou dado,
        não inventar uma anomalia para cada unidade.
        """

        return self.screens > 0 or self.fragments > 0

    @classmethod
    def of(cls, microfrontends: list[MicroFrontend]) -> "Sizes":

        if not microfrontends:
            return cls(0, 0, 0)

        return cls(
            screens=statistics.median(
                len(item.screens) for item in microfrontends
            ),
            fragments=statistics.median(
                len(item.fragments) for item in microfrontends
            ),
            code_lines=statistics.median(
                item.size.code_lines for item in microfrontends
            ),
        )


def peers(artifacts: ArtifactSet) -> list[MicroFrontend]:
    """
    Os micro frontends que entram na comparação.

    O orquestrador fica de fora: ele existe para hospedar os
    outros, e comparar o tamanho dele com o dos demais mede a coisa
    errada.
    """

    return [
        item
        for item in artifacts.microfrontends
        if item.role != "shell"
    ]
