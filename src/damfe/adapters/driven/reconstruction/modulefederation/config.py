"""
A declaração de federação, onde quer que ela esteja.

Module Federation não tem orquestrador. Não existe arquivo que
registre as unidades do sistema, como o `registerApplication` do
single-spa: cada unidade se declara no próprio arquivo de build, e o
sistema é o que emerge dessas declarações quando lidas juntas.

Três campos importam:

    name       a identidade da unidade na rede de federação
    exposes    o que ela publica, `{ "./Botao": "./src/Botao" }`
    remotes    de quem ela consome, `{ app1: "app1@http://…" }`

A mesma declaração aparece sob várias embalagens — webpack, Vite,
Rspack, o wrapper do Nx —, e todas recebem o mesmo objeto. Por isso
a busca é pelo objeto, não pelo empacotador.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Node

from damfe.adapters.driven.reconstruction.ast import AstReader

#: Como a declaração é construída, por empacotador.
#:
#: `withModuleFederation` é o embrulho do Nx sobre o plugin do
#: webpack, e `federation` é o do plugin de Vite. Procurar pelo nome
#: do plugin direto perderia os dois, que é o que acontecia antes.
DECLARATIONS = (
    "ModuleFederationPlugin",
    "withModuleFederation",
    "NxModuleFederationPlugin",
    "federation",
    "moduleFederationPlugin",
)

#: Arquivos que costumam carregá-la.
CONFIG_NAMES = (
    "webpack.config",
    "webpack.prod",
    "webpack.dev",
    "vite.config",
    "rspack.config",
    "module-federation.config",
    "federation.config",
    "next.config",
)


@dataclass
class Federation:
    """O que uma unidade declara sobre si e sobre quem ela consome."""

    name: str
    directory: Path
    declared_in: Path

    #: caminho publicado -> módulo interno
    exposes: dict[str, str] = field(default_factory=dict)

    #: apelido local -> especificador remoto
    remotes: dict[str, str] = field(default_factory=dict)

    #: dependências compartilhadas declaradas
    shared: list[str] = field(default_factory=list)


def is_config(path: Path) -> bool:

    return any(path.name.startswith(name) for name in CONFIG_NAMES)


def read(path: Path, root: Node, source: bytes) -> list[Federation]:
    """As declarações de federação contidas num arquivo."""

    found = []

    # `new ModuleFederationPlugin({...})` é `new_expression`, e
    # `withModuleFederation({...})` é `call_expression`. As duas
    # formas aparecem no mesmo ecossistema, e procurar só uma
    # devolvia declaração nenhuma num projeto webpack inteiro.
    calls = list(AstReader.find_all(root, "call_expression")) + list(
        AstReader.find_all(root, "new_expression")
    )

    for call in calls:

        function = call.child_by_field_name("constructor") or (
            call.child_by_field_name("function")
        )
        arguments = call.child_by_field_name("arguments")

        if not function or not arguments:
            continue

        name = AstReader.text(function, source).split(".")[-1].strip()

        if name not in DECLARATIONS:
            continue

        for child in arguments.named_children:

            if child.type != "object":
                continue

            federation = _from_object(child, source, path)

            if federation:
                found.append(federation)

    return found


def _from_object(node: Node, source: bytes, path: Path) -> Federation | None:

    fields = _pairs(node, source)

    if "name" not in fields:
        return None

    name = AstReader.strip_quotes(
        AstReader.text(fields["name"], source)
    ).strip()

    if not name:
        return None

    return Federation(
        name=name,
        directory=path.parent,
        declared_in=path,
        exposes=_mapping(fields.get("exposes"), source),
        remotes=_mapping(fields.get("remotes"), source),
        shared=sorted(_mapping(fields.get("shared"), source)),
    )


def _pairs(node: Node, source: bytes) -> dict[str, Node]:

    found = {}

    for pair in node.named_children:

        if pair.type != "pair":
            continue

        key_node = pair.child_by_field_name("key")
        value_node = pair.child_by_field_name("value")

        if key_node and value_node:
            found[
                AstReader.strip_quotes(AstReader.text(key_node, source))
            ] = value_node

    return found


def _mapping(node: Node | None, source: bytes) -> dict[str, str]:
    """
    Um campo que é mapa, ou lista, ou nenhum dos dois.

    `exposes` e `remotes` são objetos; `shared` costuma ser objeto mas
    também aparece como lista de nomes. Um campo montado em variável
    devolve vazio: resolvê-lo exigiria avaliar o módulo.
    """

    if node is None:
        return {}

    if node.type == "array":
        return {
            AstReader.strip_quotes(AstReader.text(child, source)): ""
            for child in node.named_children
            if child.type == "string"
        }

    if node.type != "object":
        return {}

    found = {}

    for key, value in _pairs(node, source).items():

        text = AstReader.text(value, source)

        found[key] = (
            AstReader.strip_quotes(text)
            if value.type == "string"
            else ""
        )

    return found


def package_name(directory: Path) -> str | None:
    """O nome declarado no `package.json` daquele diretório."""

    try:
        manifest = json.loads(
            (directory / "package.json").read_text(encoding="utf-8")
        )
    except Exception:
        return None

    return manifest.get("name")
