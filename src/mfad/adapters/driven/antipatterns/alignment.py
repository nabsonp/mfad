"""
A medida de tamanho do sistema, compartilhada pelas regras de
granularidade.

`nano-frontend` e `mega-frontend` perguntam a mesma coisa de lados
opostos: esta unidade é pequena ou grande demais perto das outras?
A comparação é relativa de propósito — "poucas telas" depende do
tamanho dos vizinhos, e um limiar absoluto seria um número
escolhido sem justificativa.

O corte é a CERCA DE TUKEY, `Q1 - 1.5 x IQR` e `Q3 + 1.5 x IQR`, que
é a definição corrente de outlier em estatística descritiva. Antes
eram múltiplos da mediana escolhidos por simetria — 0.4 e 2.0 —, sem
origem nenhuma. A cerca tem nome, referência e uma propriedade que
múltiplo de mediana não tem: num conjunto homogêneo ela não acusa
ninguém, em vez de acusar uma fração fixa.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from mfad.domain import MicroFrontendArchitecture, MicroFrontend


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


#: Mínimo de unidades para que quartil signifique alguma coisa.
#:
#: Com quatro pontos a interpolação inventa valores fracionários
#: sobre uma amostra de inteiros, e o quartil vira ficção. Abaixo
#: disto a regra se abstém: sistema pequeno demais para falar de
#: outlier é resposta melhor que um número inventado.
MIN_SAMPLE = 8

#: O multiplicador clássico de Tukey.
WHISKER = 1.5


@dataclass(frozen=True)
class Fences:
    """As cercas inferior e superior de uma distribuição."""

    low: float
    high: float
    q1: float
    q3: float
    iqr: float


def fences(
    values: list[float],
    min_sample: int = MIN_SAMPLE,
) -> Fences | None:
    """
    As cercas de Tukey, ou `None` quando não há o que medir.

    Uma só abstenção: amostra menor que `min_sample`, onde o quartil
    não descreve distribuição nenhuma.

    IQR zero NÃO abstém. A distribuição é constante, as duas cercas
    colapsam no mesmo ponto, e aí qualquer desvio é outlier — o que
    é coerente, porque com dispersão zero qualquer diferença está a
    uma distância infinita em IQRs. Quem usa a cerca compara com
    desigualdade ESTRITA, e então o caso degenerado se resolve: as
    unidades no próprio ponto não são acusadas, e só as que destoam
    são. Abster aqui escondia o outlier mais óbvio que existe — nove
    unidades iguais e uma sete vezes maior.
    """

    if len(values) < min_sample:
        return None

    q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")

    iqr = q3 - q1

    return Fences(
        low=q1 - WHISKER * iqr,
        high=q3 + WHISKER * iqr,
        q1=q1,
        q3=q3,
        iqr=iqr,
    )
