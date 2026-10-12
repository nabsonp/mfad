"""
Acesso ao estado global.

Dois micro frontends que leem a mesma fatia do estado estão
acoplados sem trocar mensagem e sem importar nada um do outro —
um acoplamento que nenhuma das outras extrações enxerga.

A detecção é por biblioteca conhecida, identificada pelo
especificador do import. Não há heurística de nome: o que vem de
`react-redux` é acesso a estado, chame-se a variável como se
chamar.

Nas bibliotecas, só a LEITURA é extraída.
`useSelector((state) => state.cart)` percorre o caminho
explicitamente, e é isso que se registra. A escrita —
`dispatch(addProduto(item))` — revela apenas o nome da ação no
ponto da chamada; saber que fatia ela altera exigiria seguir o
redutor, que pode nem estar no mesmo repositório.

O armazenamento do navegador — `localStorage` e `sessionStorage` —
também é estado global, e dos mais comuns entre micro frontends: o
token de autenticação gravado por um e lido por todos. Aqui leitura
e escrita entram, porque as duas dizem a chave.

Store Redux criado dentro da própria unidade não é global: é o estado
dela. Só conta o que é lido de um store que pode ser compartilhado —
criado fora, pelo orquestrador ou por um pacote comum.

A função do projeto que repassa um parâmetro seu como chave do
armazenamento — `setLocalStorageItem(key, value)` — vira acesso ao
armazenamento também, e a chave é lida em quem a chama. O acesso é
de quem chama: o utilitário pode morar num pacote comum, e é cada
micro frontend que o usa que toca aquela chave.

Acesso dentro de função que ninguém chama não conta, pelo mesmo
critério de código morto da comunicação.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Node

from damfe.adapters.driven.reconstruction.ast import AstReader, ImportTable
from damfe.adapters.driven.reconstruction.ast.symbols import (
    ModuleSymbols,
    SymbolIndex,
    unwrap,
)
from damfe.adapters.driven.reconstruction.singlespa import libraries
from damfe.adapters.driven.reconstruction.singlespa.context import ScanContext
from damfe.adapters.driven.reconstruction.singlespa.expressions import (
    EXACT,
    ExpressionEvaluator,
)
from damfe.adapters.driven.reconstruction.singlespa.forwarding import (
    Parameter,
    parameter_of,
    until_stable,
)
from damfe.adapters.driven.reconstruction.singlespa.liveness import Liveness
from damfe.adapters.driven.reconstruction.singlespa.ownership import Ownership
from damfe.domain import MicroFrontend, SourceLocation, StateAccess


#: Pedaço de chave: texto conhecido, parâmetro, ou `None` para valor
#: que não se resolve.
Part = str | Parameter | None


@dataclass(frozen=True)
class Forward:
    """Um acesso que a função faz com a chave que recebe."""

    #: `localStorage` ou `sessionStorage`
    kind: str

    #: posição do parâmetro que é a chave
    index: int

    #: texto que a função põe antes e depois da chave recebida
    prefix: str
    suffix: str

    access: str


@dataclass(frozen=True)
class Target:
    """Uma chamada que acessa o armazenamento, e de onde sai a chave."""

    kind: str
    access: str
    key: Node
    prefix: str = ""
    suffix: str = ""


class GlobalStateExtractor:

    def __init__(
        self,
        context: ScanContext,
        microfrontends: list[MicroFrontend],
    ):
        self.context = context

        self.ownership = Ownership(context.repository, microfrontends)

        self.known = {item.id for item in microfrontends}

        self.evaluator = ExpressionEvaluator(context.routes)

        #: unidades que criam o próprio store Redux
        self.private_stores: set[str] = set()

        self.index: SymbolIndex = context.symbols()

        self.liveness = Liveness(context)

        #: (arquivo, função) → acessos que ela faz com a chave recebida
        self.wrappers: dict[tuple[Path, str], set[Forward]] = {}

        #: o último nome de cada embrulhadora, para só resolver a
        #: chamada que pode ser uma delas
        self._wrapper_names: set[str] = set()

    def extract(self) -> list[StateAccess]:

        self.private_stores = self._private_stores()

        files = [
            symbols
            for file_path in self.context.tree.source_files()
            if (symbols := self.index.of(file_path)) is not None
        ]

        until_stable(files, self._find_wrappers)

        found: list[StateAccess] = []

        for symbols in files:
            found.extend(self._from_file(symbols.path, symbols))

        return sorted(
            found,
            key=lambda item: (
                item.microfrontend,
                item.path,
                item.at.file,
                item.at.line,
            ),
        )

    def _from_file(
        self,
        file_path: Path,
        symbols: ModuleSymbols,
    ) -> list[StateAccess]:

        owner = self.ownership.of_file(file_path)

        # Acesso em pacote compartilhado não é acoplamento entre
        # micro frontends: não há de quem para quem.
        if owner not in self.known:
            return []

        root, source = symbols.root, symbols.source

        bindings = self._bindings(root, source)

        relative = self.context.relative(file_path)

        found: list[StateAccess] = []

        def at(node: Node) -> SourceLocation:
            return SourceLocation(
                file=relative,
                line=node.start_point.row + 1,
                code=self._line(node, source),
            )

        for node in AstReader.find_all(root, "call_expression"):

            function = node.child_by_field_name("function")

            if not function:
                continue

            targets = self._targets(node, symbols)

            if targets:

                if not self.liveness.is_live(node, symbols):
                    continue

                for target in targets:

                    key = self._complete_key(target, symbols)

                    if key:
                        found.append(
                            StateAccess(
                                microfrontend=owner,
                                library=target.kind,
                                path=key,
                                at=at(node),
                                access=target.access,
                            )
                        )

                continue

            if function.type != "identifier":
                continue

            entry = bindings.get(AstReader.text(function, source))

            if not entry:
                continue

            library, kind = entry

            # Store criado dentro da própria unidade é estado local, por
            # mais que use a mesma biblioteca que as outras.
            if library.module == "react-redux" and owner in self.private_stores:
                continue

            if not self.liveness.is_live(node, symbols):
                continue

            for path in self._accesses(node, source, kind):

                found.append(
                    StateAccess(
                        microfrontend=owner,
                        library=library.name,
                        path=path,
                        at=at(node),
                    )
                )

        return found

    def _private_stores(self) -> set[str]:
        """As unidades em cujo código um store Redux é criado."""

        factories = set(libraries.REDUX_STORE_FACTORIES)

        found: set[str] = set()

        for file_path in self.context.tree.source_files():

            owner = self.ownership.of_file(file_path)

            if owner not in self.known or owner in found:
                continue

            try:
                root, source = self.context.reader.parse(file_path)
            except Exception:
                continue

            local = {
                record.local_name
                for record in ImportTable.records(root, source)
                if (record.module, record.imported_name) in factories
            }

            if not local:
                continue

            for node in AstReader.find_all(root, "call_expression"):

                function = node.child_by_field_name("function")

                if function is not None and AstReader.text(function, source) in local:
                    found.add(owner)
                    break

        return found

    # ------------------------------------------------------------------
    # Quem é o quê neste arquivo
    # ------------------------------------------------------------------

    @staticmethod
    def _bindings(
        root: Node,
        source: bytes,
    ) -> dict[str, tuple[libraries.StateLibrary, str]]:
        """Nome local -> (biblioteca, papel da função)."""

        by_module = {
            library.module: library
            for library in libraries.STATE_LIBRARIES
        }

        bindings: dict[str, tuple[libraries.StateLibrary, str]] = {}

        for record in ImportTable.records(root, source):

            library = by_module.get(record.module)

            if not library:
                continue

            for kind, names in (
                ("selector", library.selectors),
                ("atom", library.atoms),
            ):
                if record.imported_name in names:
                    bindings[record.local_name] = (library, kind)

        return bindings

    # ------------------------------------------------------------------
    # Armazenamento do navegador
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Armazenamento do navegador
    # ------------------------------------------------------------------

    def _targets(self, node: Node, symbols: ModuleSymbols) -> list[Target]:
        """Os acessos ao armazenamento que a chamada faz, direto ou por embrulhadora."""

        direct = self._storage(node, symbols)

        return [direct] if direct else self._wrapper_call(node, symbols)

    def _storage(self, node: Node, symbols: ModuleSymbols) -> Target | None:
        """
        `localStorage.setItem(chave, …)` e `getItem(chave)`.

        O receptor precisa ser o próprio `localStorage` ou
        `sessionStorage`: um `cache.getItem("x")` qualquer não é
        armazenamento compartilhado, e casar só pelo nome do método
        transformaria toda classe com `getItem` num estado global.
        """

        function = unwrap(node.child_by_field_name("function"))

        if function is None or function.type != "member_expression":
            return None

        method = function.child_by_field_name("property")
        receiver = function.child_by_field_name("object")

        if not method or not receiver:
            return None

        name = symbols.text(method)

        if name not in libraries.STORAGE_WRITE + libraries.STORAGE_READ:
            return None

        # Aceita `localStorage` e `window.localStorage`.
        kind = symbols.text(receiver).rpartition(".")[2]

        if kind not in libraries.STORAGES:
            return None

        arguments = self._arguments(node)

        if not arguments:
            return None

        access = "write" if name in libraries.STORAGE_WRITE else "read"

        return Target(kind=kind, access=access, key=arguments[0])

    def _wrapper_call(self, node: Node, symbols: ModuleSymbols) -> list[Target]:
        """Chamada a uma função do projeto que repassa a chave."""

        function = unwrap(node.child_by_field_name("function"))

        if function is None:
            return []

        name = function.child_by_field_name("property") if function.type == "member_expression" else function

        if name is None or symbols.text(name) not in self._wrapper_names:
            return []

        callee = self.index.callee(node, symbols)

        forwards = self.wrappers.get(callee, set()) if callee else set()

        arguments = self._arguments(node)

        return [
            Target(
                kind=forward.kind,
                access=forward.access,
                key=arguments[forward.index],
                prefix=forward.prefix,
                suffix=forward.suffix,
            )
            for forward in sorted(forwards, key=lambda item: (item.access, item.kind, item.index))
            if forward.index < len(arguments)
        ]

    def _find_wrappers(self, node: Node, symbols: ModuleSymbols) -> bool:
        """
        A função em volta, se ela repassa um parâmetro como a chave.

        A chave tem de ser o parâmetro, com no máximo texto conhecido
        antes e depois: `key`, `` `app:${key}` ``, `"pref." + key`.
        """

        found = False

        for target in self._targets(node, symbols):

            parts = [target.prefix, *self._key_parts(target.key, symbols), target.suffix]

            tails = [index for index, part in enumerate(parts) if isinstance(part, Parameter)]

            if len(tails) != 1 or any(part is None for part in parts):
                continue

            parameter = parts[tails[0]]

            key = self.index.key_of(parameter.function, symbols)

            if key is None:
                continue

            forward = Forward(
                kind=target.kind,
                index=parameter.index,
                prefix="".join(parts[: tails[0]]),
                suffix="".join(parts[tails[0] + 1 :]),
                access=target.access,
            )

            forwards = self.wrappers.setdefault((symbols.path, key), set())

            if forward not in forwards:
                forwards.add(forward)
                self._wrapper_names.add(key.rpartition(".")[2])
                found = True

        return found

    def _complete_key(self, target: Target, symbols: ModuleSymbols) -> str | None:
        """A chave inteira, quando toda ela é conhecida."""

        parts = [target.prefix, *self._key_parts(target.key, symbols), target.suffix]

        if not all(isinstance(part, str) for part in parts):
            return None

        return "".join(parts) or None

    def _key_parts(self, node: Node, symbols: ModuleSymbols) -> list[Part]:
        """
        Os pedaços da chave.

        Só literal ou constante resolvível, nunca o nome do
        identificador. A chave é o contrato: duas unidades se
        acoplam por tocarem a MESMA string. Cair no nome da variável
        junta qualquer par de arquivos que, por coincidência, chame
        a sua de `storageKey` — foi o que aconteceu com dois theme
        providers copiados, que nada tinham entre si.

        O preço é perder a chave montada em variável. Vale: inventar
        acoplamento é pior do que não achar um.
        """

        node = unwrap(node)

        if node is None:
            return [None]

        if node.type == "identifier":

            parameter = parameter_of(node, symbols)

            if parameter is not None:
                return [parameter]

        if node.type in ("string", "identifier", "template_string", "binary_expression"):

            key = self._key(node, symbols.source)

            if key is not None:
                return [key]

        if node.type == "template_string":
            return self._template_parts(node, symbols)

        if node.type == "binary_expression":

            operator = node.child_by_field_name("operator")

            if operator is None or symbols.text(operator) != "+":
                return [None]

            return self._key_parts(node.child_by_field_name("left"), symbols) + self._key_parts(
                node.child_by_field_name("right"), symbols
            )

        return [self._key(node, symbols.source)]

    def _template_parts(self, node: Node, symbols: ModuleSymbols) -> list[Part]:

        parts: list[Part] = []

        position = node.start_byte + 1

        for child in node.named_children:

            if child.type != "template_substitution":
                continue

            if child.start_byte > position:
                parts.append(symbols.source[position:child.start_byte].decode("utf-8", "replace"))

            inner = [item for item in child.named_children if item.type != "comment"]

            parts.extend(self._key_parts(inner[0], symbols) if inner else [None])

            position = child.end_byte

        if node.end_byte - 1 > position:
            parts.append(symbols.source[position:node.end_byte - 1].decode("utf-8", "replace"))

        return parts

    def _key(self, node: Node | None, source: bytes) -> str | None:

        if node is None:
            return None

        if node.type == "string":
            return AstReader.strip_quotes(AstReader.text(node, source))

        value = self.evaluator.evaluate(node, source)

        # Só chave inteira: `"cart_" + id` não diz qual fatia é, e o
        # começo dela juntaria chaves diferentes numa só.
        if not value or value.match != EXACT or value.based:
            return None

        return value.url

    # ------------------------------------------------------------------
    # Leituras
    # ------------------------------------------------------------------

    def _accesses(
        self,
        node: Node,
        source: bytes,
        kind: str,
    ) -> list[str]:

        arguments = self._arguments(node)

        if not arguments:
            return []

        if kind == "atom":

            name = AstReader.text(arguments[0], source).strip()

            return [name] if name.isidentifier() else []

        if kind == "selector":
            return self._paths(arguments[0], source)

        return []

    def _paths(self, selector: Node, source: bytes) -> list[str]:
        """
        Os caminhos que um seletor percorre.

        `(state) => state.cart` devolve `cart`. Um seletor que monta
        objeto — `(state) => ({ user: state.user, cart: state.cart })` —
        devolve os dois: são duas fatias lidas, não uma.
        """

        parameter = self._first_parameter(selector, source)

        if not parameter:
            return []

        body = selector.child_by_field_name("body") or selector

        paths: list[str] = []

        for node in AstReader.find_all(body, "member_expression"):

            path = self._path_from(node, source, parameter)

            if path and path not in paths:
                paths.append(path)

        return paths

    @staticmethod
    def _first_parameter(selector: Node, source: bytes) -> str | None:

        if selector.type not in {
            "arrow_function",
            "function_expression",
            "function_declaration",
        }:
            return None

        parameter = selector.child_by_field_name("parameter")

        if parameter:
            return AstReader.text(parameter, source)

        parameters = selector.child_by_field_name("parameters")

        if not parameters:
            return None

        for child in parameters.named_children:

            if child.type == "identifier":
                return AstReader.text(child, source)

        return None

    @staticmethod
    def _path_from(
        node: Node,
        source: bytes,
        parameter: str,
    ) -> str | None:
        """
        `state.user.profile` vira `user.profile`.

        Só a expressão mais externa interessa: as internas são
        prefixos dela e contariam a mesma leitura duas vezes.
        """

        if node.parent and node.parent.type == "member_expression":
            return None

        text = AstReader.text(node, source)

        head, _, rest = text.partition(".")

        if head.strip() != parameter or not rest:
            return None

        return rest.strip()

    # ------------------------------------------------------------------

    @staticmethod
    def _arguments(node: Node) -> list[Node]:

        arguments = node.child_by_field_name("arguments")

        if not arguments:
            return []

        return [
            child
            for child in arguments.named_children
            if child.type != "comment"
        ]

    @staticmethod
    def _line(node: Node, source: bytes) -> str:

        return " ".join(AstReader.text(node, source).split())[:160]
