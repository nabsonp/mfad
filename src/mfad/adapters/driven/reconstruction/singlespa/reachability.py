"""
Alcance entre arquivos de um mesmo micro frontend.

Chamadas a serviço raramente moram na tela. O padrão comum é a tela
importar um módulo de serviço, que importa outro, que finalmente
faz a chamada — e sem seguir essa cadeia o endpoint fica atribuído
ao arquivo onde a chamada está, que não diz nada sobre quem o usa.

Este módulo resolve isso percorrendo os imports RELATIVOS, que são
os internos ao micro frontend, os apelidos do `tsconfig` que caem
dentro do mesmo pacote, e — no Angular — os componentes que
o template usa pelo seletor, que a tela renderiza sem importar.
Imports de pacote ficam de fora de propósito: atravessar a fronteira
do pacote seria sair da unidade, e é justamente a fronteira que
interessa preservar.

O percurso é iterativo e guarda os visitados, porque grafo de
módulo tem ciclo com frequência — dois arquivos que se importam
mutuamente são comuns e legítimos.
"""

from __future__ import annotations

from pathlib import Path

from mfad.domain import MicroFrontend, Placement
from mfad.adapters.driven.reconstruction.ast import ImportTable, ModuleResolver
from mfad.adapters.driven.reconstruction.singlespa.context import ScanContext


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
        """Os arquivos do mesmo micro frontend que este importa."""

        if file_path in self._direct:
            return self._direct[file_path]

        found: set[Path] = set()

        try:
            root, source = self.context.reader.parse(file_path)
        except Exception:
            self._direct[file_path] = found
            return found

        package = self.context.package_dir(file_path)

        for record in ImportTable.records(root, source):

            target = ModuleResolver.resolve(record.module, file_path)

            if not target:
                continue

            # Apelido do `tsconfig` (`@/utils/x`) é import interno do
            # projeto, mas `paths` também pode apontar para o pacote
            # vizinho de um monorepo — e aí é fronteira, como import de
            # pacote.
            if not record.module.startswith(".") and package not in target.parents:
                continue

            found.add(target)

        # No Angular a tela não importa o que renderiza: o template
        # usa o seletor. Sem isto, tudo abaixo da tela ficava fora.
        found |= self.context.templates().used_by(file_path)

        self._direct[file_path] = found

        return found


def placements(
    context: ScanContext,
    microfrontends: list[MicroFrontend],
) -> dict[str, Placement]:
    """
    Arquivo relativo → telas e fragmentos que o alcançam.

    Invertido de propósito: a extração encontra a instanciação ou a
    ponta de um canal e precisa perguntar quem chega até ali, não o
    contrário. Telas e fragmentos ficam separados porque só a tela
    é lugar; o fragmento é o caminho pelo qual o código de outro
    micro frontend chega a uma tela.
    """

    reachability = Reachability(context)

    screens: dict[str, set[str]] = {}
    fragments: dict[str, set[str]] = {}

    origins = [
        (screen.file, screen.id, screens)
        for microfrontend in microfrontends
        for screen in microfrontend.screens
    ] + [
        (fragment.file, fragment.id, fragments)
        for microfrontend in microfrontends
        for fragment in microfrontend.fragments
    ]

    for relative, identifier, target in origins:

        if not relative:
            continue

        origin = context.repository / relative

        if not origin.is_file():
            continue

        for reached in reachability.reachable_from(origin):
            target.setdefault(context.relative(reached), set()).add(identifier)

    return {
        path: Placement(
            screens=sorted(screens.get(path, ())),
            fragments=sorted(fragments.get(path, ())),
        )
        for path in set(screens) | set(fragments)
    }


def placement_of(
    found: dict[str, Placement],
    files: list[str],
) -> Placement:
    """A união do alcance de vários arquivos — as várias pontas de um lado."""

    screens: set[str] = set()
    fragments: set[str] = set()

    for file in files:

        item = found.get(file)

        if item:
            screens.update(item.screens)
            fragments.update(item.fragments)

    return Placement(screens=sorted(screens), fragments=sorted(fragments))
