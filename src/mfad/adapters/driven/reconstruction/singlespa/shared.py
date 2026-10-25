"""
Código de pacote compartilhado, contado para quem o importa.

Um pacote do corpus que não é unidade — a biblioteca comum do
monorepo, o repositório `common` de uma organização — não roda
sozinho: roda dentro de cada micro frontend que o importa. A chamada
HTTP ou o acesso ao `localStorage` que mora nele acontece em cada um
desses micro frontends, e é deles. O local registrado continua sendo
o do pacote, que é onde está o código.
"""

from __future__ import annotations

from pathlib import Path

from mfad.adapters.driven.reconstruction.ast import ImportTable, ModuleResolver
from mfad.adapters.driven.reconstruction.ast.resolver import canonical
from mfad.adapters.driven.reconstruction.singlespa.context import ScanContext
from mfad.adapters.driven.reconstruction.singlespa.ownership import Ownership
from mfad.adapters.driven.reconstruction.ast.symbols import SymbolIndex
from mfad.domain import MicroFrontend


def importers(context: ScanContext, microfrontends: list[MicroFrontend]) -> dict[Path, set[str]]:
    """Arquivo de pacote compartilhado → as unidades que o importam."""

    key = ("shared",) + tuple(item.id for item in microfrontends)

    if key in context._api:
        return context._api[key]

    ownership = Ownership(context.repository, microfrontends)

    index = context.symbols()

    reached: dict[Path, set[Path]] = {}

    found: dict[Path, set[str]] = {}

    for file_path in context.tree.source_files():

        owner = ownership.of_file(file_path)

        if owner is None:
            continue

        try:
            root, source = context.reader.parse(file_path)
        except Exception:
            continue

        for record in ImportTable.records(root, source):

            # Import de pacote: o que o projeto resolve sozinho já é dele.
            if record.module.startswith(".") or ModuleResolver.resolve(record.module, file_path) is not None:
                continue

            entry = context.package_entry(record.module)

            if entry is None or ownership.of_file(entry) is not None:
                continue

            entry = canonical(entry)

            if entry not in reached:
                reached[entry] = _inside(index, entry, context.package_dir(entry))

            for path in reached[entry]:
                found.setdefault(path, set()).add(owner)

    context._api[key] = found

    return found


def _inside(index: SymbolIndex, entry: Path, package: Path) -> set[Path]:
    """
    Os arquivos do pacote que a entrada alcança: imports e reexports
    (`export * from "./x"`, o `index` de toda biblioteca), sem sair dele.
    """

    seen: set[Path] = set()

    pending = [entry]

    while pending:

        current = pending.pop()

        if current in seen:
            continue

        seen.add(current)

        symbols = index.of(current)

        if symbols is None:
            continue

        modules = [module for module, _ in symbols.imports.values()] + [module for module, _ in symbols.reexports]

        for module in modules:

            target = ModuleResolver.resolve(module, current)

            if target is not None and package in canonical(target).parents:
                pending.append(canonical(target))

    return seen
