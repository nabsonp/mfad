"""
Descoberta de unidades de baixo para cima.

O caminho usual parte do orquestrador: lê `registerApplication` e
aprende quais aplicações existem. Ele falha sempre que o registro não
está escrito como literal no código — e isso é comum em sistema real,
não exceção:

    applications.forEach(registerApplication)   // single-spa-layout
    System.import(name); mountRootParcel(app)   // parcel + import map

Nos dois casos as aplicações existem, estão no repositório, e o
registro não as nomeia em lugar nenhum que a árvore sintática alcance.

Aqui a pergunta é invertida. Um pacote cujo módulo de entrada exporta
os ciclos de vida do single-spa — `bootstrap`, `mount` e `unmount` —
**é** um micro frontend, tenha sido registrado onde for. O contrato é
do framework, não do projeto, e vale mesmo quando ninguém o registra
no código analisado.
"""

from __future__ import annotations

from pathlib import Path

from mfad.adapters.driven.reconstruction.singlespa.context import (
    Registration,
    ScanContext,
)

#: Os três que caracterizam a unidade. `update` é opcional no
#: framework, então exigi-lo perderia unidades legítimas.
REQUIRED = frozenset({"bootstrap", "mount", "unmount"})


def by_lifecycles(
    context: ScanContext,
    exports_of,
    taken: set[Path],
    in_scope,
) -> list[Registration]:
    """
    Registros sintéticos para as unidades achadas pelos ciclos de vida.

    `taken` traz os DIRETÓRIOS que a descoberta de cima para baixo já
    cobriu. A deduplicação é por diretório, e não por nome, porque os
    dois caminhos nomeiam a unidade de formas diferentes: o registro
    usa o especificador do import map, este usa o `name` do
    `package.json`. Comparar nomes deixaria a mesma unidade entrar
    duas vezes com identidades distintas.

    Quando as duas acham a mesma unidade, o registro real prevalece —
    ele carrega `activeWhen` e `customProps`, que o arquivo de entrada
    não tem.
    """

    found: dict[str, Registration] = {}

    for file_path in context.tree.source_files():

        try:
            root, source = context.reader.parse(file_path)
        except Exception:
            continue

        lifecycles, _ = exports_of(root, source)

        if not REQUIRED.issubset(set(lifecycles)):
            continue

        directory = context.package_dir(file_path).resolve()

        if directory in taken or not _installable(directory):
            continue

        name = _package_name(directory) or directory.name

        if name in found or not in_scope(name):
            continue

        taken.add(directory)

        found[name] = Registration(
            name=name,
            active_when=[],
            specifier=None,
            declared_in=file_path,
            active_when_form="absent",
            entrypoint=file_path,
        )

    return [found[name] for name in sorted(found)]


def _package_name(directory: Path) -> str | None:

    import json

    manifest = directory / "package.json"

    if not manifest.is_file():
        return None

    try:
        return json.loads(manifest.read_text(encoding="utf-8")).get("name")
    except Exception:
        return None


def _installable(directory: Path) -> bool:
    """
    Se o pacote pode ser instalado e construído: sem `package.json` vale
    o diretório, mas um `package.json` que não é JSON (o modelo de um
    gerador, com `"name": "<%= name %>"`) o npm recusa
    (https://docs.npmjs.com/cli/configuring-npm/package-json). É molde
    de micro frontend, não um.
    """

    import json

    manifest = directory / "package.json"

    if not manifest.is_file():
        return True

    try:
        json.loads(manifest.read_text(encoding="utf-8"))
    except Exception:
        return False

    return True
