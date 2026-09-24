"""
Portas condutoras — o lado esquerdo do hexágono.

Definem como o mundo externo aciona a aplicação. Quem implementa
o outro lado é um adaptador condutor (`adapters/driving`): hoje o
CLI, amanhã uma API, sem que os casos de uso mudem.

O caso de uso devolve um RESULTADO, não texto nem código de saída.
Formatar e decidir o status do processo são responsabilidades do
adaptador — é o que mantém a aplicação livre de apresentação.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar


T = TypeVar("T")


class UseCase(ABC, Generic[T]):
    """
    Uma operação da aplicação, no padrão Command.

    O objeto carrega tudo de que precisa e sabe se executar.
    Falhas viram exceção de `damfe.application.errors`.
    """

    @abstractmethod
    def execute(self) -> T:
        """Executa e devolve o resultado."""
