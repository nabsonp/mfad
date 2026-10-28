"""
Driving ports — the left side of the hexagon.

They define how the outside world drives the application. The other
side is implemented by a driving adapter (`adapters/driving`): the
CLI today, an API tomorrow, without the use cases changing.

The use case returns a RESULT, not text or an exit code. Formatting
and deciding the process status are the adapter's responsibilities —
that is what keeps the application free of presentation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar


T = TypeVar("T")


class UseCase(ABC, Generic[T]):
    """
    An application operation, following the Command pattern.

    The object carries everything it needs and knows how to execute
    itself. Failures become exceptions from `mfad.application.errors`.
    """

    @abstractmethod
    def execute(self) -> T:
        """Executes and returns the result."""
