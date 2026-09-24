"""
Alcance entre arquivos de um mesmo micro frontend.

Chamadas a serviço raramente moram na tela. O padrão comum é a tela
importar um módulo de serviço, que importa outro, que finalmente
faz a chamada — e sem seguir essa cadeia o endpoint fica atribuído
ao arquivo onde a chamada está, que não diz nada sobre quem o usa.

Este módulo resolve isso percorrendo os imports RELATIVOS, que são
os internos ao micro frontend. Imports de pacote ficam de fora de
propósito: atravessar a fronteira do pacote seria sair da unidade,
e é justamente a fronteira que interessa preservar.

O percurso é iterativo e guarda os visitados, porque grafo de
módulo tem ciclo com frequência — dois arquivos que se importam
mutuamente são comuns e legítimos.
"""

from __future__ import annotations

from pathlib import Path

from damfe.adapters.driven.reconstruction.ast import ImportTable, ModuleResolver
from damfe.adapters.driven.reconstruction.singlespa.context import ScanContext


class Reachability:

    def __init__(self, context: ScanContext):

        self.context = context

        self._direct: dict[Path, set[Path]] = {}

        self._closure: dict[Path, set[Path]] = {}

    def reachable_from(self, origin: Path) -> set[Path]:
        """
        Os arquivos que `origin` alcança, incluindo ele mesmo.

        O resultado é memorizado: uma tela e um fragmento da mesma
        pasta costumam alcançar quase o mesmo conjunto.
        """

        if origin in self._closure:
            return self._closure[origin]

        seen: set[Path] = set()

        pending = [origin]

        while pending:

            current = pending.pop()

            if current in seen:
                continue

            seen.add(current)

            pending.extend(self._imports_of(current) - seen)

        self._closure[origin] = seen

        return seen

    def _imports_of(self, file_path: Path) -> set[Path]:
        """Os arquivos que este importa por caminho relativo."""

        if file_path in self._direct:
            return self._direct[file_path]

        found: set[Path] = set()

        try:
            root, source = self.context.reader.parse(file_path)
        except Exception:
            self._direct[file_path] = found
            return found

        for record in ImportTable.records(root, source):

            if not record.module.startswith("."):
                continue

            target = ModuleResolver.resolve(record.module, file_path)

            if target:
                found.add(target)

        self._direct[file_path] = found

        return found
