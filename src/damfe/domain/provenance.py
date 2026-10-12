"""
Procedência: de onde os artefatos vieram e sob qual esquema.

Sem isto um conjunto de artefatos é anônimo — não diz qual versão
da ferramenta o produziu, nem de qual revisão de qual repositório.
Para a avaliação empírica isso é fatal: o resultado deixa de ser
reproduzível no momento em que o repositório analisado recebe um
commit.
"""

from __future__ import annotations

from dataclasses import dataclass, field


#: Versão do ESQUEMA dos artefatos, não da ferramenta.
#:
#: Sobe quando a forma dos arquivos muda de um jeito que quebra
#: quem os lê. Separada de `__version__` de propósito: correção de
#: bug no extrator muda a ferramenta e não o esquema, e durante uma
#: coleta longa é preciso poder dizer "todos os resultados são
#: esquema 1.0.0" mesmo tendo trocado de versão no meio.
SCHEMA_VERSION = "3.3.0"


@dataclass
class SourceRepository:
    """Um repositório analisado, na revisão em que foi analisado."""

    #: caminho relativo à raiz da análise. Nunca absoluto — o
    #: artefato é versionado, e caminho de máquina sujaria o diff.
    path: str

    #: URL de origem, sem credencial.
    remote: str = ""

    #: SHA completo do HEAD, vazio quando não é um repositório git.
    commit: str = ""

    #: Havia alteração não commitada no momento da análise. Quando
    #: verdadeiro, o `commit` NÃO identifica o que foi lido.
    dirty: bool = False


@dataclass
class Provenance:
    """O cabeçalho que torna um conjunto de artefatos autodescritivo."""

    schema: str = SCHEMA_VERSION
    tool: str = ""
    generated_at: str = ""
    reconstructor: str = ""
    sources: list[SourceRepository] = field(default_factory=list)

    def source(self, path: str) -> SourceRepository | None:

        for repository in self.sources:

            if repository.path == path:
                return repository

        return None
