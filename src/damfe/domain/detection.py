"""O anti-padrão do catálogo e as ocorrências dele — neutros como o resto."""

from __future__ import annotations

from dataclasses import dataclass, field

from damfe.domain.model import SourceLocation


@dataclass(frozen=True)
class AntiPattern:
    """
    Uma entrada do catálogo de anti-padrões.

    Existe independentemente de qualquer análise: `cyclic-dependency`
    é um anti-padrão descrito na literatura, tenha ou não sido
    encontrado em algum sistema. É O QUÊ.

    Distinto da `Rule`, que é o COMO — a porta que sabe procurá-lo
    nos artefatos. Uma mesma entrada do catálogo poderia ter mais de
    uma operacionalização, e nenhuma delas muda o que o anti-padrão é.

    E distinto da `AntiPatternDetection`, que é uma ocorrência: este
    é o tipo, aquela é a instância.
    """

    #: identificador estável, ex.: "cyclic-dependency"
    name: str

    description: str

    #: a categoria do catálogo de origem
    category: str = ""

    #: onde o anti-padrão está descrito
    reference: str = ""


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

    `anti_pattern` é o NOME da entrada do catálogo, não o objeto —
    como toda referência neste modelo.
    """

    anti_pattern: str
    message: str
    dimension: str = ""
    explanation: str = ""
    subjects: list[str] = field(default_factory=list)
    locations: list[SourceLocation] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    #: onde o anti-padrão está descrito no catálogo: a definição para
    #: quem avalia a ocorrência sem conhecê-lo
    reference: str = ""
