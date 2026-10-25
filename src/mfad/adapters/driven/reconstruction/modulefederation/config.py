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

from mfad.adapters.driven.reconstruction.ast import AstReader

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
    # Num arquivo cujo nome existe só para conter a declaração, o
    # objeto pode estar exportado sem chamada alguma em volta.
    if path.name.startswith(("module-federation.config", "federation.config")):

        exported = exported_object(root, source)

        if exported is not None:

            federation = _from_object(exported, source, path, root)

            if federation:
                found.append(federation)

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

            # `federation({...})` — o literal está ali.
            if child.type == "object":
                candidate = child

            # `federation(config)` — o literal está noutro lugar do
            # mesmo arquivo. É a forma canônica do Nx, e a que o
            # plugin de Vite também aceita; sem resolver o
            # identificador, um projeto inteiro lê como se não
            # tivesse federação nenhuma.
            elif child.type == "identifier":
                candidate = _declared_object(
                    root, AstReader.text(child, source), source
                )

            else:
                candidate = None

            if candidate is None:
                continue

            federation = _from_object(candidate, source, path, root)

            if federation:
                found.append(federation)

    return found


def exported_object(root: Node, source: bytes) -> Node | None:
    """
    O literal de objeto que o arquivo exporta por padrão.

    `export default { name, exposes }`, ou `export default config`
    com o objeto declarado acima. É como o Nx escreve o
    `module-federation.config.ts`: o arquivo existe só para conter a
    declaração, e não há chamada nenhuma para procurar dentro.
    """

    for node in AstReader.find_all(root, "export_statement"):

        value = node.child_by_field_name("value")

        if value is None:
            continue

        if value.type == "object":
            return value

        if value.type == "identifier":
            resolved = _declared_object(
                root, AstReader.text(value, source), source
            )

            if resolved is not None:
                return resolved

    return None


def _declared_object(root: Node, name: str, source: bytes) -> Node | None:
    """O literal de objeto atribuído a `name` neste arquivo."""

    for declarator in AstReader.find_all(root, "variable_declarator"):

        target = declarator.child_by_field_name("name")
        value = declarator.child_by_field_name("value")

        if target is None or value is None:
            continue

        if AstReader.text(target, source) != name:
            continue

        # `const config: ModuleFederationConfig = {...}` — a anotação
        # de tipo fica entre o nome e o valor, e o valor continua
        # sendo o objeto.
        if value.type == "object":
            return value

    return None


def _from_object(
    node: Node,
    source: bytes,
    path: Path,
    root: Node | None = None,
) -> Federation | None:

    fields = _pairs(node, source, root)

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


def _pairs(
    node: Node,
    source: bytes,
    root: Node | None = None,
) -> dict[str, Node]:

    found = {}

    for pair in node.named_children:

        # `federation({ ...remoteConfig })` — o literal existe, mas o
        # que interessa está no objeto espalhado dentro dele. Sem
        # resolver, o campo `name` não aparece e a declaração é
        # descartada como se não fosse uma.
        if pair.type == "spread_element" and root is not None:

            for child in pair.named_children:

                if child.type != "identifier":
                    continue

                target = _declared_object(
                    root, AstReader.text(child, source), source
                )

                if target is not None:
                    found.update(_pairs(target, source, root))

            continue

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
