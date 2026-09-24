"""Guardar o acesso a um modelo de linguagem."""

from __future__ import annotations

from damfe.application.ports import SettingsRepository, UseCase
from damfe.application.results import LlmSetupResult
from damfe.application.settings import LlmSettings


class SetupLlmUseCase(UseCase[LlmSetupResult]):

    def __init__(
        self,
        settings: SettingsRepository,
        endpoint: str | None = None,
        model: str | None = None,
        key: str | None = None,
    ):
        self.settings = settings

        self.endpoint = endpoint
        self.model = model
        self.key = key

    def execute(self) -> LlmSetupResult:

        current = self.settings.load_llm()

        # Só o que veio é alterado: informar apenas o modelo não
        # deve apagar a credencial já guardada.
        merged = LlmSettings(
            endpoint=self.endpoint or current.endpoint,
            model=self.model or current.model,
            key=self.key or current.key,
        )

        if not any([self.endpoint, self.model, self.key]):
            return LlmSetupResult(settings=current, written=None)

        return LlmSetupResult(
            settings=merged,
            written=self.settings.save_llm(merged),
        )
