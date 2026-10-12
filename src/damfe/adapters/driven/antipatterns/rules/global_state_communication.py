"""
Estado global usado como canal entre micro frontends.

Quando mais de um micro frontend acessa a mesma fatia do estado,
o estado deixou de ser detalhe interno de um e virou meio de
comunicação entre vários — sem contrato declarado, sem mensagem e
sem import. O formato daquele dado passa a ser interface pública
de fato, e mudá-lo quebra todos os que o tocam ao mesmo tempo.

Vale para biblioteca de estado e para o armazenamento do navegador:
uma chave do `localStorage` tocada por vários micro frontends é a
mesma coisa que uma fatia do store lida por vários.

A fatia é identificada pela biblioteca E pelo caminho. A chave
`user` do `localStorage` e a fatia `user` de um store Redux são
dados diferentes, e juntá-las pelo nome acusaria acoplamento que
não existe.

A ocorrência é ÚNICA e binária: ou o sistema usa estado global
como canal, ou não usa. Emitir uma por fatia diria a mesma coisa
várias vezes — o que interessa saber é se a prática existe, e
quem participa dela.
"""

from __future__ import annotations

from damfe.adapters.driven import i18n
from damfe.application.ports import Rule
from damfe.domain import (
    AntiPattern,
    AntiPatternDetection,
    MicroFrontendArchitecture,
    StateAccess,
)


def _slice(access: StateAccess) -> str:
    """`localStorage:token`, `react-redux:cart` — o mesmo rótulo das arestas."""

    return f"{access.library}:{access.path}"


class GlobalStateCommunication(Rule):

    anti_pattern = AntiPattern(
        name="global-state-communication",
        description=(
            "Estado global acessado por mais de um micro frontend, "
            "funcionando como canal de comunicação não declarado."
        ),
        category="Inter-frontend",
        reference="https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Global%20state%20communication",
    )

    def __init__(self, min_microfrontends: int = 2):

        #: A partir de quantos acessantes o estado deixa de ser
        #: interno e passa a ser canal. Dois já bastam.
        self.min_microfrontends = min_microfrontends

    def check(self, architecture: MicroFrontendArchitecture) -> list[AntiPatternDetection]:

        readers = self._readers(architecture)

        shared = {
            path: holders
            for path, holders in readers.items()
            if len(holders) >= self.min_microfrontends
        }

        if not shared:
            return []

        involved = sorted(
            {holder for holders in shared.values() for holder in holders}
        )

        text = {
            "dimension": i18n.ref("dimension.global_state"),
            "explanation": i18n.ref("gsc.explanation"),
            "message": i18n.ref(
                "gsc.message",
                n=len(involved),
                slices=len(shared),
                names=", ".join(self._short(item) for item in involved),
            ),
        }

        # Quem está envolvido já é a coluna da linha, e cada fatia, com
        # quem lê, quem grava e onde, sai de `metadata.slices`.
        text["facts"] = [i18n.fact("fact.slices", len(shared))]

        return [
            AntiPatternDetection(
                anti_pattern=self.name,
                dimension=i18n.t(text["dimension"]),
                explanation=i18n.t(text["explanation"]),
                message=i18n.t(text["message"]),
                subjects=involved,
                locations=self._locations(architecture, shared),
                metadata={
                    "text": text,
                    "relation": "shared_state",
                    "edges": self._edges(shared),
                    "slices": {
                        path: sorted(holders)
                        for path, holders in sorted(shared.items())
                    },
                    "libraries": sorted(
                        {item.library for item in architecture.state_accesses}
                    ),
                },
            )
        ]

    @staticmethod
    def _readers(architecture: MicroFrontendArchitecture) -> dict[str, set[str]]:

        readers: dict[str, set[str]] = {}

        for access in architecture.state_accesses:
            readers.setdefault(_slice(access), set()).add(access.microfrontend)

        return readers

    @staticmethod
    def _edges(shared: dict[str, set[str]]) -> list[list[str]]:
        """
        Os pares que leem a mesma fatia, nos dois sentidos — a
        relação não tem direção, e o desenho traça um arco por
        ordem.
        """

        pairs: list[list[str]] = []

        for holders in shared.values():

            ordered = sorted(holders)

            for source in ordered:
                for target in ordered:

                    if source != target and [source, target] not in pairs:
                        pairs.append([source, target])

        return pairs

    @staticmethod
    def _locations(architecture: MicroFrontendArchitecture, shared: dict) -> list:

        # Uma linha pode tocar duas fatias; ela aparece uma vez só.
        found: dict[tuple, object] = {}

        for access in architecture.state_accesses:

            if _slice(access) in shared:
                found.setdefault((access.at.file, access.at.line), access.at)

        return list(found.values())

    @staticmethod
    def _short(name: str) -> str:

        return name.rpartition("/")[2] or name
