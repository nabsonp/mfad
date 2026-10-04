"""
Portas conduzidas — o lado direito do hexágono.

Definem o que a aplicação precisa do mundo externo. Quem as
implementa são os adaptadores conduzidos (`adapters/driven`):
o extrator de single-spa, o armazenamento em JSON, e assim por
diante. A aplicação depende destas abstrações, nunca deles.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from damfe.domain import (
    ApiCall,
    MicroFrontend,
    MicroFrontendArchitecture,
    Communication,
    CommunicationSpec,
    AntiPattern,
    AntiPatternDetection,
    Composition,
    Navigation,
    SourceRepository,
    StateAccess,
)


class Reconstructor(ABC):
    """
    Extrai artefatos arquiteturais de um repositório.

    Uma implementação por tecnologia de micro frontend.

    A porta é segmentada por TIPO de artefato, não numa única
    operação: quem só quer o inventário de aplicações não paga
    pela extração dos imports. Cada método é um passo que um
    caso de uso pode acionar isoladamente.
    """

    #: identificador usado no CLI, ex.: "single-spa"
    name: str = ""

    #: descrição curta
    description: str = ""

    @abstractmethod
    def detect(self, repository: Path) -> bool:
        """Diz se este reconstrutor reconhece o repositório."""

    @abstractmethod
    def microfrontends(self, repository: Path) -> list[MicroFrontend]:
        """As unidades de implantação e o que cada uma contém."""

    @abstractmethod
    def compositions(
        self,
        repository: Path,
        microfrontends: list[MicroFrontend],
    ) -> list[Composition]:
        """
        O consumo de fragmentos através das fronteiras.

        Recebe as aplicações já extraídas porque é o catálogo
        delas que distingue um fragmento de um export qualquer.
        """

    @abstractmethod
    def navigations(
        self,
        repository: Path,
        microfrontends: list[MicroFrontend],
    ) -> list[Navigation]:
        """
        As navegações que cruzam a fronteira entre aplicações.

        Recebe as aplicações já extraídas porque são as rotas
        declaradas por elas que dizem de quem é cada destino.
        """

    @abstractmethod
    def communications(
        self,
        repository: Path,
        microfrontends: list[MicroFrontend],
        spec: CommunicationSpec,
    ) -> list[Communication]:
        """
        A troca de mensagens entre aplicações.

        Depende da `spec`: sem mecanismo declarado não há o que
        procurar, e o resultado é vazio. É a única extração que
        precisa de configuração, porque é a única sem contrato
        padrão no ecossistema.
        """


class SourceProbe(ABC):
    """
    Identifica a revisão de cada repositório analisado.

    Existe para que a procedência seja responsabilidade de um
    adaptador: ler o estado do git é I/O, e o caso de uso só
    precisa do resultado. Uma implementação que não encontre git
    nenhum devolve lista vazia — a análise não depende disto.
    """

    @abstractmethod
    def describe(self, root: Path) -> list[SourceRepository]:
        """Os repositórios sob `root`, em ordem estável."""


class Rule(ABC):
    """
    Como procurar um anti-padrão nos artefatos.

    A regra é o COMO; o `AntiPattern` que ela declara é o QUÊ. São
    separados porque uma mesma entrada do catálogo admite mais de
    uma operacionalização, e trocar de operacionalização não muda o
    que o anti-padrão é.

    Opera somente sobre o modelo de domínio — por isso a detecção é
    agnóstica à tecnologia de origem.
    """

    #: a entrada do catálogo que esta regra procura
    anti_pattern: AntiPattern

    @property
    def name(self) -> str:
        return self.anti_pattern.name

    @property
    def description(self) -> str:
        return self.anti_pattern.description

    @abstractmethod
    def check(self, architecture: MicroFrontendArchitecture) -> list[AntiPatternDetection]:
        """Avalia os artefatos e devolve as ocorrências."""


class Renderer(ABC):
    """Serializa artefatos e anti-padrões em algum formato visual."""

    #: identificador usado no CLI, ex.: "mermaid"
    name: str = ""

    #: extensão sugerida para o arquivo de saída
    extension: str = "txt"

    @abstractmethod
    def render(
        self,
        architecture: MicroFrontendArchitecture,
        detections: list[AntiPatternDetection] | None = None,
    ) -> str:
        """Devolve a representação como texto."""


class SpecRepository(ABC):
    """
    Leitura e escrita da declaração de comunicação.

    Separada do `ArtifactRepository` porque a spec é ENTRADA da
    análise, escrita uma vez no setup, enquanto os artefatos são
    saída, reescritos a cada execução.
    """

    @abstractmethod
    def load_communication(self, source: Path) -> CommunicationSpec:
        ...

    @abstractmethod
    def save_communication(
        self,
        spec: CommunicationSpec,
        destination: Path,
    ) -> Path:
        ...


class ArtifactRepository(ABC):
    """
    Persistência de artefatos e anti-padrões.

    Abstraída para que os casos de uso não conheçam o formato
    nem o meio de armazenamento.
    """

    @abstractmethod
    def save(
        self,
        architecture: MicroFrontendArchitecture,
        destination: Path,
    ) -> list[Path]:
        ...

    @abstractmethod
    def load(self, source: Path) -> MicroFrontendArchitecture:
        ...

    @abstractmethod
    def save_detections(
        self,
        detections: list[AntiPatternDetection],
        destination: Path,
    ) -> Path:
        ...

    @abstractmethod
    def load_detections(self, source: Path) -> list[AntiPatternDetection]:
        ...
