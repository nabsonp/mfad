"""
The communication declaration, in YAML.

A file written at setup and read on every analysis. It is the input
that makes communication extraction deterministic: the same file
always produces the same result, and it is readable and reviewable,
unlike a query generated at run time.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from mfad.application.ports import SpecRepository
from mfad.domain import (
    ChannelOperation,
    CommunicationSpec,
    Mechanism,
)


#: Setup folder, at the root of the analyzed repository. It sits next to
#: the code because the declaration is an INPUT of the analysis: versioned
#: with the project and immune to any cleanup of the output folder.
SETUP_DIRECTORY = ".mfad"

COMMUNICATION = "communication.yml"

TEMPLATE = """\
# How the applications of this system talk to each other.
#
# Each mechanism has two sides: who produces and who consumes. They
# are paired by the CHANNEL NAME, which is the argument given by
# `channel_argument` (0-based).
#
# Fill in with your project's real functions and remove the example.

mechanisms:
  - name: events
    kind: pubsub
    produce:
      module: "@your-org/utils"
      export: publishEvent
      channel_argument: 0
    consume:
      module: "@your-org/utils"
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
        Accepts the file itself or the folder that contains it.

        A folder already named `.mfad` gets the file inside it; any
        other is treated as a repository root, and the setup folder
        is created there.
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
