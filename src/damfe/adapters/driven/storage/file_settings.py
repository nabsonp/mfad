"""
Configuração do modelo de linguagem, no diretório do usuário.

**Nunca no repositório analisado.** O `.damfe/` é versionado junto
com o projeto, e uma credencial ali seria commitada e publicada com
ele. Isso mora em `~/.config/damfe/`, com permissão de leitura só
para o dono.

A variável de ambiente tem precedência sobre o arquivo — é o que
permite usar outra credencial numa execução isolada, ou num
ambiente de integração contínua, sem reescrever a configuração.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from damfe.application.ports import SettingsRepository
from damfe.application.settings import DEFAULT_ENDPOINT, LlmSettings


ENV_ENDPOINT = "DAMFE_LLM_URL"
ENV_MODEL = "DAMFE_LLM_MODEL"
ENV_KEY = "DAMFE_LLM_KEY"


class FileSettingsRepository(SettingsRepository):

    def __init__(self, home: Path | None = None):

        base = home or Path(
            os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
        )

        self.path = base / "damfe" / "config.json"

    def load_llm(self) -> LlmSettings:

        stored = self._read()

        return LlmSettings(
            endpoint=(
                os.environ.get(ENV_ENDPOINT)
                or stored.get("endpoint")
                or DEFAULT_ENDPOINT
            ),
            model=os.environ.get(ENV_MODEL) or stored.get("model", ""),
            key=os.environ.get(ENV_KEY) or stored.get("key", ""),
        )

    def save_llm(self, settings: LlmSettings) -> Path:

        self.path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "endpoint": settings.endpoint,
            "model": settings.model,
            "key": settings.key,
        }

        # Cria com 0600 desde o início: escrever e depois ajustar
        # deixaria uma janela com o arquivo legível por outros.
        descriptor = os.open(
            self.path,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )

        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2)
            file.write("\n")

        return self.path

    def _read(self) -> dict:

        if not self.path.is_file():
            return {}

        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}
