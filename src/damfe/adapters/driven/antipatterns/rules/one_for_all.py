"""
Um micro frontend conectado a quase todos os outros.

O sintoma é um micro frontend que toca praticamente todo o
sistema — seja porque todos dependem dele, seja porque ele
depende de todos. Nos dois casos ele deixa de ser uma parte
implantável de forma independente e vira o centro do sistema:
qualquer mudança nele repercute em toda parte, e ele precisa
acompanhar a evolução de todos.

A conexão é contada sem direção. Depender de todos e ser
dependido por todos são problemas diferentes — a proporção de
cada um vai no metadata —, mas ambos caracterizam o mesmo
acoplamento excessivo.

Arestas simétricas não entram. O estado global vira, na
reconstrução, uma aresta entre cada par de quem toca a mesma fatia
— uma chave de token lida por todos liga todos a todos, e a regra
acusaria quase o sistema inteiro por um acoplamento que não tem
centro. Esse acoplamento já tem regra própria, o
`global-state-communication`.
"""

from __future__ import annotations

from collections import defaultdict

from damfe.adapters.driven import i18n
from damfe.application.ports import Rule
from damfe.domain import AntiPattern, AntiPatternDetection, MicroFrontendArchitecture


class OneForAll(Rule):

    anti_pattern = AntiPattern(
        name="one-for-all",
        description=(
            "Micro frontend conectado a quase todos os outros, por "
            "fragmento, navegação ou comunicação."
        ),
        category="Inter-frontend",
        reference="https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/One%20Micro%20Frontend%20for%20all",
    )

    def __init__(
        self,
        ratio: float = 0.9,
        min_microfrontends: int = 5,
    ):
        #: Fração dos demais a que o micro frontend precisa estar
        #: conectado para ser acusado.
        self.ratio = ratio

        #: Piso de tamanho do sistema. Num sistema pequeno, estar
        #: conectado a todos os outros é o normal, não um desvio —
        #: abaixo deste tamanho a regra se abstém em vez de acusar
        #: todo mundo.
        self.min_microfrontends = min_microfrontends

    def check(self, architecture: MicroFrontendArchitecture) -> list[AntiPatternDetection]:

        # O orquestrador é excluído: alcançar todos é a função
        # dele. Mantê-lo no cálculo ainda inflaria o grau de todos
        # os outros, já que ele navega para o sistema inteiro.
        peers = [
            microfrontend.id
            for microfrontend in architecture.microfrontends
            if microfrontend.role != "shell"
        ]

        if len(peers) < self.min_microfrontends:
            return []

        known = set(peers)

        outgoing, incoming = self._degrees(architecture, known)

        detections: list[AntiPatternDetection] = []

        for peer in peers:

            others = len(known) - 1

            neighbours = (outgoing[peer] | incoming[peer]) - {peer}

            if len(neighbours) < self.ratio * others:
                continue

            detections.append(
                self._detection(
                    peer,
                    neighbours,
                    others,
                    outgoing[peer],
                    incoming[peer],
                )
            )

        return detections

    @staticmethod
    def _degrees(
        architecture: MicroFrontendArchitecture,
        known: set[str],
    ) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
        """Vizinhos de saída e de entrada, unindo as três relações."""

        outgoing: dict[str, set[str]] = defaultdict(set)
        incoming: dict[str, set[str]] = defaultdict(set)

        edges = (
            [
                (item.consumer, item.provider)
                for item in architecture.compositions
            ]
            + [
                (item.source, item.target)
                for item in architecture.navigations
            ]
            + [
                (item.source, item.target)
                for item in architecture.communications
                # O teste é a propriedade, não o mecanismo, como no
                # cyclic-dependency.
                if item.directed
            ]
        )

        for source, target in edges:

            if source not in known or target not in known:
                continue

            outgoing[source].add(target)
            incoming[target].add(source)

        return outgoing, incoming

    def _detection(
        self,
        peer: str,
        neighbours: set[str],
        others: int,
        outgoing: set[str],
        incoming: set[str],
    ) -> AntiPatternDetection:

        text = {
            "dimension": i18n.ref("dimension.all_relations"),
            "explanation": i18n.ref("ofa.explanation"),
            "message": i18n.ref(
                "ofa.message",
                name=self._short(peer),
                neighbours=len(neighbours),
                others=others,
                out=len(outgoing),
                incoming=len(incoming),
            ),
        }

        text["facts"] = [
            i18n.fact("fact.connected", i18n.ref("fact.of", part=len(neighbours), whole=others)),
            i18n.fact("fact.depends_on", len(outgoing)),
            i18n.fact("fact.depended_by", len(incoming)),
        ]

        return AntiPatternDetection(
            anti_pattern=self.name,
            dimension=i18n.t(text["dimension"]),
            explanation=i18n.t(text["explanation"]),
            message=i18n.t(text["message"]),
            subjects=[peer, *sorted(neighbours)],
            metadata={
                "text": text,
                "edges": (
                    [[peer, other] for other in sorted(outgoing)]
                    + [[other, peer] for other in sorted(incoming)]
                ),
                "neighbours": len(neighbours),
                "others": others,
                "coverage": round(len(neighbours) / others, 2)
                if others
                else 0,
                "depends_on": sorted(outgoing),
                "depended_on_by": sorted(incoming),
            },
        )

    @staticmethod
    def _short(name: str) -> str:

        return name.rpartition("/")[2] or name
