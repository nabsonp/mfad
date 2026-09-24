"""
Configuração de acesso a um modelo de linguagem.

Não é entidade de domínio: não descreve arquitetura, descreve como
alcançar um serviço. Fica aqui, na aplicação, porque é o caso de
uso que precisa dela — e não no `domain/`, que só guarda o que a
análise reconstrói.
"""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_ENDPOINT = "https://openrouter.ai/api/v1"


@dataclass
class LlmSettings:
    """
    Onde falar, com que modelo, com que credencial.

    `key` vazio é estado válido: um servidor local não exige
    credencial nenhuma.
    """

    endpoint: str = DEFAULT_ENDPOINT
    model: str = ""
    key: str = ""

    def __bool__(self) -> bool:
        return bool(self.endpoint and self.model)

    @property
    def masked_key(self) -> str:
        """A chave como se mostra em tela: só o final."""

        if not self.key:
            return "—"

        return f"…{self.key[-6:]}" if len(self.key) > 6 else "…"
