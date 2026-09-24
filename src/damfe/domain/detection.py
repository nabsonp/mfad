"""O resultado de uma regra — neutro como o resto do modelo."""

from __future__ import annotations

from dataclasses import dataclass, field

from damfe.domain.model import SourceLocation


@dataclass
class AntiPatternDetection:
    """
    Uma ocorrência de anti-padrão.

    Deliberadamente SEM severidade. Atribuir "alta" ou "baixa" a um
    anti-padrão exigiria uma escala definida e justificada, e
    inventá-la daria ares de medida ao que seria opinião. O que a
    ocorrência informa no lugar é `dimension`: qual relação
    arquitetural a produziu — porque um ciclo de composição e um
    ciclo de navegação são anti-padrões diferentes, e essa
    diferença é observável nos artefatos, não arbitrada.

    `subjects` guarda os identificadores envolvidos, e `metadata` o
    que é próprio de cada regra, para que a apresentação represente
    cada anti-padrão sem conhecê-lo.
    """

    rule: str
    message: str
    dimension: str = ""
    explanation: str = ""
    subjects: list[str] = field(default_factory=list)
    locations: list[SourceLocation] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
