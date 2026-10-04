"""
A medida de tamanho do sistema, compartilhada pelas regras de
granularidade.

`nano-frontend` e `mega-frontend` perguntam a mesma coisa de lados
opostos: esta unidade é pequena ou grande demais perto das outras?
A comparação é relativa de propósito — "poucas telas" depende do
tamanho dos vizinhos, e um limiar absoluto seria um número
escolhido sem justificativa.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from damfe.domain import MicroFrontendArchitecture, MicroFrontend


@dataclass
class Sizes:
    """As medianas do sistema, em telas, fragmentos e linhas."""

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
        certo é a regra se abster e o relatório dizer que faltou
        dado, não inventar uma anomalia para cada unidade.
        """

        return self.screens > 0 or self.fragments > 0

    @classmethod
    def of(cls, microfrontends: list[MicroFrontend]) -> "Sizes":

        if not microfrontends:
            return cls(screens=0, fragments=0, code_lines=0)

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


def peers(architecture: MicroFrontendArchitecture) -> list[MicroFrontend]:
    """
    Os micro frontends que entram na comparação.

    O orquestrador fica de fora: ele existe para hospedar os
    outros, e comparar o tamanho dele com o dos demais mede a coisa
    errada.
    """

    return [
        item
        for item in architecture.microfrontends
        if item.role != "shell"
    ]
