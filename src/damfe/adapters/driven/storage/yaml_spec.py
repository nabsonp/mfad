"""
A declaração de comunicação, em YAML.

Arquivo escrito no setup e lido a cada análise. É a entrada que
torna a extração de comunicação determinística: o mesmo arquivo
produz sempre o mesmo resultado, e ele é legível e revisável —
diferente de uma query gerada em tempo de execução.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from damfe.application.ports import SpecRepository
from damfe.domain import (
    ChannelOperation,
    CommunicationSpec,
    Mechanism,
)


#: Pasta de setup, na raiz do repositório analisado. Fica junto do
#: código porque a declaração é ENTRADA da análise: versionada com
#: o projeto e imune a qualquer limpeza da pasta de saída.
SETUP_DIRECTORY = ".damfe"

COMMUNICATION = "communication.yml"

TEMPLATE = """\
# Como as aplicações deste sistema conversam entre si.
#
# Cada mecanismo tem dois lados: quem produz e quem consome. O
# pareamento entre eles é feito pelo NOME DO CANAL, que é o
# argumento indicado por `channel_argument` (base 0).
#
# Preencha com as funções reais do seu projeto e remova o exemplo.

mechanisms:
  - name: eventos
    kind: pubsub
    produce:
      module: "@sua-org/utils"
      export: publishEvent
      channel_argument: 0
    consume:
      module: "@sua-org/utils"
      export: subscribeToTopic
      channel_argument: 0
"""


class YamlSpecRepository(SpecRepository):

    def load_communication(self, source: Path) -> CommunicationSpec:

        path = self._path(source)

        if not path.is_file():
            return CommunicationSpec()

        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

        return CommunicationSpec(
            mechanisms=[
                self._mechanism(item)
                for item in payload.get("mechanisms", [])
            ]
        )

    def save_communication(
        self,
        spec: CommunicationSpec,
        destination: Path,
    ) -> Path:

        path = self._path(destination)

        path.parent.mkdir(parents=True, exist_ok=True)

        if not spec:
            path.write_text(TEMPLATE, encoding="utf-8")
            return path

        payload = {
            "mechanisms": [
                {
                    "name": mechanism.name,
                    "kind": mechanism.kind,
                    "produce": self._operation(mechanism.produce),
                    "consume": self._operation(mechanism.consume),
                }
                for mechanism in spec.mechanisms
            ]
        }

        path.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

        return path

    # ------------------------------------------------------------------

    @staticmethod
    def _path(location: Path, filename: str = COMMUNICATION) -> Path:
        """
        Aceita o arquivo direto ou a pasta que o contém.

        Uma pasta já chamada `.damfe` recebe o arquivo dentro dela;
        qualquer outra é tratada como raiz de repositório, e a
        pasta de setup é criada ali.
        """

        if location.suffix in {".yml", ".yaml"}:
            return location

        if location.name == SETUP_DIRECTORY:
            return location / filename

        return location / SETUP_DIRECTORY / filename

    @classmethod
    def _mechanism(cls, payload: dict) -> Mechanism:

        return Mechanism(
            name=payload.get("name", "?"),
            kind=payload.get("kind", "pubsub"),
            produce=cls._channel(payload.get("produce", {})),
            consume=cls._channel(payload.get("consume", {})),
        )

    @staticmethod
    def _channel(payload: dict) -> ChannelOperation:

        return ChannelOperation(
            module=payload.get("module", ""),
            export=payload.get("export", ""),
            channel_argument=payload.get("channel_argument", 0),
        )

    @staticmethod
    def _operation(operation: ChannelOperation) -> dict:

        return {
            "module": operation.module,
            "export": operation.export,
            "channel_argument": operation.channel_argument,
        }
