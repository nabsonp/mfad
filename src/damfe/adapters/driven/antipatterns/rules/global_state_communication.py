"""
Estado global usado como canal entre micro frontends.

Quando mais de um micro frontend lê a mesma fatia do estado, o
estado deixou de ser detalhe interno de um e virou meio de
comunicação entre vários — sem contrato declarado, sem mensagem e
sem import. O formato daquele dado passa a ser interface pública
de fato, e mudá-lo quebra todos os leitores ao mesmo tempo.

A ocorrência é ÚNICA e binária: ou o sistema usa estado global
como canal, ou não usa. Emitir uma por fatia diria a mesma coisa
várias vezes — o que interessa saber é se a prática existe, e
quem participa dela.
"""

from __future__ import annotations

from damfe.application.ports import Rule
from damfe.domain import AntiPatternDetection, ArtifactSet


class GlobalStateCommunication(Rule):

    name = "global-state-communication"

    description = (
        "Estado global lido por mais de um micro frontend, "
        "funcionando como canal de comunicação não declarado."
    )

    def __init__(self, min_microfrontends: int = 2):

        #: A partir de quantos leitores o estado deixa de ser
        #: interno e passa a ser canal. Dois já bastam.
        self.min_microfrontends = min_microfrontends

    def check(self, artifacts: ArtifactSet) -> list[AntiPatternDetection]:

        readers = self._readers(artifacts)

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

        return [
            AntiPatternDetection(
                rule=self.name,
                dimension="estado global",
                explanation=(
                    "Mais de um micro frontend lê a mesma fatia do "
                    "estado global. O formato desse dado virou "
                    "interface pública de fato, sem nunca ter sido "
                    "declarado como tal."
                ),
                message=(
                    f"{len(involved)} micro frontends compartilham "
                    f"{len(shared)} "
                    + ("fatia" if len(shared) == 1 else "fatias")
                    + " do estado global: "
                    + ", ".join(self._short(item) for item in involved)
                ),
                subjects=involved,
                locations=self._locations(artifacts, shared),
                metadata={
                    "relation": "shared_state",
                    "edges": self._edges(shared),
                    "slices": {
                        path: sorted(holders)
                        for path, holders in sorted(shared.items())
                    },
                    "libraries": sorted(
                        {item.library for item in artifacts.state_accesses}
                    ),
                },
            )
        ]

    @staticmethod
    def _readers(artifacts: ArtifactSet) -> dict[str, set[str]]:

        readers: dict[str, set[str]] = {}

        for access in artifacts.state_accesses:
            readers.setdefault(access.path, set()).add(access.microfrontend)

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
    def _locations(artifacts: ArtifactSet, shared: dict) -> list:

        return [
            access.at
            for access in artifacts.state_accesses
            if access.path in shared
        ]

    @staticmethod
    def _short(name: str) -> str:

        return name.rpartition("/")[2] or name
