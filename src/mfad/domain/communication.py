"""
Comunicação entre aplicações e a declaração do mecanismo.

Ao contrário de rota e de fragmento, comunicação não tem contrato
único no ecossistema: cada projeto escolhe barramento de eventos,
store compartilhado, `window`, `postMessage`. Por isso o mecanismo
é DECLARADO uma vez, num momento de setup, e a extração passa a
ser determinística como as demais.

`Communication` é o resultado; `CommunicationSpec` é a declaração.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mfad.domain.model import Placement, SourceLocation, StateAccess


@dataclass
class ChannelOperation:
    """
    Um lado do mecanismo: quem publica ou quem assina.

    `module` e `export` identificam a função; `channel_argument`
    diz em qual posição dos argumentos está o nome do canal.
    """

    module: str
    export: str
    channel_argument: int = 0


@dataclass
class Mechanism:
    """Um meio de comunicação declarado pelo usuário."""

    name: str
    kind: str
    produce: ChannelOperation
    consume: ChannelOperation


@dataclass
class CommunicationSpec:
    """O que o setup gravou. Vazio significa setup não feito."""

    mechanisms: list[Mechanism] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.mechanisms)


@dataclass
class Communication:
    """
    Aresta: uma aplicação publica num canal que outra assina.

    Produtores e consumidores são pareados pelo NOME DO CANAL, não
    por chamada — é o canal que é o contrato entre as duas pontas.
    """

    source: str
    target: str
    mechanism: str
    channel: str
    produced_at: list[SourceLocation] = field(default_factory=list)
    consumed_at: list[SourceLocation] = field(default_factory=list)

    #: Telas e fragmentos que alcançam cada ponta.
    #:
    #: Os dois lados de um canal só conversam de fato quando estão
    #: montados ao mesmo tempo. Sem saber onde cada ponta está, um
    #: produtor numa tela e um consumidor noutra viravam aresta, e o
    #: grafo ligava partes que nunca coexistem.
    produced_on: Placement = field(default_factory=Placement)
    consumed_on: Placement = field(default_factory=Placement)

    #: Se o sentido da aresta significa alguma coisa.
    #:
    #: Mensagem tem lado: quem publica não é quem assina. Acoplamento
    #: por estado compartilhado não tem — os dois leem, nenhum é a
    #: origem —, e a simetria é representada por um par de arestas
    #: opostas, por falta de um tipo não direcionado na coleção.
    #:
    #: Quem percorre o grafo precisa saber a diferença. Buscar ciclo
    #: entre arestas simétricas encontra um em toda dupla, e o ciclo
    #: é a codificação, não o sistema.
    directed: bool = True


def edges_from_state(accesses: list[StateAccess]) -> list[Communication]:
    """
    Acoplamento por estado global, como arestas do mesmo grafo.

    Quando dois micro frontends leem a mesma fatia, o formato
    daquele dado virou interface pública de fato entre eles: mudá-lo
    quebra os dois de uma vez. Isso é comunicação, ainda que não
    passe mensagem nenhuma, e deixá-la fora do grafo fazia as regras
    que o percorrem — ciclo, hub — subcontarem o acoplamento real.

    A aresta é NÃO DIRECIONADA, e é aí que ela difere de todas as
    outras desta coleção. Mensagem tem lado: alguém publica, alguém
    assina. Leitura compartilhada não tem — três leitores da mesma
    fatia dependem uns dos outros mutuamente, sem que nenhum seja a
    origem. Como `Communication` tem `source` e `target`, cada par
    vira DUAS arestas, uma em cada sentido, e o par é ordenado por
    nome para que o resultado não dependa da ordem de extração.

    Só a leitura entra, porque só ela é extraída — ver `StateAccess`
    sobre por que a escrita fica de fora.
    """

    by_path: dict[tuple[str, str], set[str]] = {}
    locations: dict[tuple[str, str, str], list[SourceLocation]] = {}

    for access in accesses:

        key = (access.library, access.path)

        by_path.setdefault(key, set()).add(access.microfrontend)

        locations.setdefault(
            (access.library, access.path, access.microfrontend), []
        ).append(access.at)

    edges = []

    for (library, path), readers in sorted(by_path.items()):

        if len(readers) < 2:
            continue

        for source in sorted(readers):
            for target in sorted(readers):

                if source == target:
                    continue

                edges.append(
                    Communication(
                        source=source,
                        target=target,
                        mechanism="global-state",
                        channel=f"{library}:{path}",
                        produced_at=locations[(library, path, source)],
                        consumed_at=locations[(library, path, target)],
                        directed=False,
                    )
                )

    return edges
