"""
As unidades federadas e o que cada uma contém.

A diferença para single-spa está aqui, e só aqui. Lá existe um
orquestrador que declara todo mundo; aqui cada unidade se declara, e
o sistema é o que emerge quando as declarações são lidas juntas.

Três consequências que mudam a extração:

Não há `activeWhen`. Module Federation resolve carregamento de código
remoto e não diz nada sobre URL. As rotas de uma unidade são as do
roteador dela, e só existem se ela tiver um.

Não há papel de shell declarado. Quem hospeda e quem é hospedado não
são exclusivos: uma unidade pode consumir remotos e ser consumida ao
mesmo tempo. O que se pode afirmar é quem consome sem ser consumido,
e é isso que se marca.

Fragmento é o `exposes`, que é declaração explícita — melhor sinal do
que qualquer export nomeado, que é o que sobra no single-spa.
"""

from __future__ import annotations

from pathlib import Path

from damfe.domain import Fragment, MicroFrontend, Screen
from damfe.adapters.driven.reconstruction.ast import AstReader, ImportTable, ModuleResolver
from damfe.adapters.driven.reconstruction.routers import (
    AngularRouteReader,
    ReactRouteReader,
)
from damfe.adapters.driven.reconstruction.singlespa.context import ScanContext
from damfe.adapters.driven.reconstruction.modulefederation import (
    config,
    specifiers,
)


class FederatedBuilder:

    def __init__(self, context: ScanContext, federations: list):
        self.context = context
        self.federations = federations

        #: unidade -> caminhos publicados, sem o "./"
        self.catalog = {
            federation.name: {
                path.lstrip("./") for path in federation.exposes
            }
            for federation in federations
        }

        self.by_name = {
            federation.name: federation for federation in federations
        }

    def build(self) -> list[MicroFrontend]:

        consumed = {
            remote
            for federation in self.federations
            for remote in federation.remotes
        }

        found = []

        for federation in self.federations:

            found.append(self._one(federation, consumed))

        self._reattribute(found)

        return found

    def _reattribute(self, microfrontends: list[MicroFrontend]) -> None:
        """
        Devolve ao provedor a tela que o shell só rotela.

        `<Route path="/pharmacy" element={<Pharmacy/>}/>` com
        `Pharmacy` vindo de `import("hs-pharmacy/Pharmacy")` declara
        uma rota do shell para uma tela que é do remoto. A rota existe
        no roteador de quem hospeda; a tela é de quem publica.

        Deixar as duas com o hospedeiro dava um shell dono de todas as
        rotas de negócio e remotos sem rota nenhuma — o oposto do que
        o sistema faz. `_screens` já marca o provedor em
        `screen.microfrontend`; aqui as telas são movidas.
        """

        index = {item.id: item for item in microfrontends}

        for item in microfrontends:

            keep = []

            for screen in item.screens:

                target = index.get(screen.microfrontend)

                if target is None or target is item:
                    keep.append(screen)
                    continue

                target.screens.append(screen)

            item.screens = keep

        for item in microfrontends:

            item.routes = sorted(
                {screen.route for screen in item.screens if screen.route}
            )

    def _one(self, federation, consumed: set[str]) -> MicroFrontend:

        directory = self.context.package_dir(federation.declared_in)

        microfrontend = MicroFrontend(
            id=federation.name,
            directory=self.context.relative(directory),
            entrypoint=self.context.relative(federation.declared_in),
            size=self.context.size_of(directory),
        )

        published = config.package_name(directory)

        if published and published != federation.name:
            microfrontend.metadata["package"] = published

        barrels = 0

        for path, target in sorted(federation.exposes.items()):

            resolved = self._resolve(directory, target)

            microfrontend.fragments.append(
                Fragment(
                    name=path,
                    microfrontend=federation.name,
                    file=resolved,
                )
            )

            barrels += self._reexports(resolved)

        # Forma de biblioteca: o módulo exposto só reexporta, em vez
        # de definir o que publica. A unidade entrega um catálogo de
        # peças, não uma peça.
        #
        # É sinal, não classificação. Biblioteca que exponha componente
        # por componente não tem barril, e remoto pode expor um barril
        # de páginas — o formato acerta o caso comum e não prova a
        # natureza da coisa. Quem decide se aquilo é biblioteca é quem
        # lê, e é por isso que o número fica registrado em vez de mudar
        # o comportamento das regras.
        if barrels:
            microfrontend.metadata["reexports"] = barrels

        if federation.remotes:
            microfrontend.metadata["remotes"] = sorted(federation.remotes)

        if federation.shared:
            microfrontend.metadata["shared"] = federation.shared

        # Consome remotos e não é consumida por ninguém: é a ponta da
        # composição, que é o mais próximo de um shell que Module
        # Federation define. Quando todos se consomem, ninguém é.
        if federation.remotes and federation.name not in consumed:
            microfrontend.role = "shell"
            microfrontend.mounts = sorted(federation.remotes)

        microfrontend.screens = self._screens(directory, federation.name)

        microfrontend.routes = sorted(
            {screen.route for screen in microfrontend.screens if screen.route}
        )

        return microfrontend

    def _remote_names(self, root, source) -> dict[str, tuple[str, str]]:
        """
        Nome local -> (unidade publicadora, caminho publicado).

        Cobre as duas formas de atravessar a fronteira: o import
        estático e o `import()` dinâmico, que é como um host carrega
        página remota.
        """

        records = [
            (record.module, record.local_name)
            for record in ImportTable.records(root, source)
        ] + [
            (module, local_name)
            for module, local_name, _, _ in specifiers.dynamic_imports(
                root, source
            )
        ]

        found = {}

        for module, local_name in records:

            provider, exposed = specifiers.split(module, self.catalog)

            if provider:
                found[local_name] = (provider, exposed)

        return found

    def _exposed_file(self, provider: str, exposed: str) -> str | None:
        """O arquivo interno que o provedor publica sob esse caminho."""

        federation = self.by_name.get(provider)

        if not federation:
            return None

        target = (
            federation.exposes.get(f"./{exposed}")
            or federation.exposes.get(exposed)
        )

        if not target:
            return None

        return self._resolve(
            self.context.package_dir(federation.declared_in), target
        )

    def _resolve(self, directory: Path, target: str) -> str | None:
        """O arquivo interno que um `exposes` aponta."""

        if not target:
            return None

        base = (directory / target).resolve()

        # Acrescentar a extensão vem antes de trocar o sufixo:
        # `./x.component` é `x.component.ts`, não `x.ts`.
        for candidate in [base] + [
            base.parent / f"{base.name}{extension}"
            for extension in (".js", ".jsx", ".ts", ".tsx")
        ] + [
            base.with_suffix(extension)
            for extension in (".js", ".jsx", ".ts", ".tsx")
        ] + [
            base / f"index{extension}"
            for extension in (".js", ".jsx", ".ts", ".tsx")
        ]:
            if candidate.is_file():
                return self.context.relative(candidate)

        return None

    def _reexports(self, relative: str | None) -> int:
        """
        Quantos nomes o módulo reexporta sem definir.

        `export { Card } from "./ui/card"` conta; `export default
        function Pharmacy()` não. Zero significa que o módulo define o
        que publica.
        """

        if not relative:
            return 0

        path = self.context.repository / relative

        if not path.is_file():
            return 0

        try:
            root, source = self.context.reader.parse(path)
        except Exception:
            return 0

        found = 0

        for node in AstReader.find_all(root, "export_statement"):

            text = AstReader.text(node, source)

            if " from " not in text:
                continue

            for clause in node.named_children:

                if clause.type != "export_clause":
                    continue

                found += sum(
                    1
                    for child in clause.named_children
                    if child.type == "export_specifier"
                )

        return found

    def _screens(self, directory: Path, owner: str) -> list[Screen]:
        """
        As telas declaradas pelo roteador da própria unidade.

        Sem `activeWhen` não há rota vinda do registro, então tela
        aqui só existe quando a unidade tem roteador. Uma unidade que
        só publica componentes não tem tela nenhuma, e isso é o
        resultado correto — ela não responde por URL alguma.
        """

        found: list[Screen] = []

        seen: set[tuple[str, str]] = set()

        directory = directory.resolve()

        for file_path in sorted(
            path
            for path in self.context.tree.source_files()
            if directory in path.resolve().parents
        ):
            try:
                root, source = self.context.reader.parse(file_path)
            except Exception:
                continue

            imports = ImportTable(root, source, file_path)

            for screen in AngularRouteReader(self.context).screens_in(
                file_path, owner
            ):
                key = (screen.component, screen.route or "")

                if key in seen:
                    continue

                seen.add(key)
                found.append(screen)

            # Nome local -> unidade que o publica, para as duas formas
            # de atravessar a fronteira: `import X from "remote/X"` e
            # `const X = lazy(() => import("remote/X"))`.
            remote_of = self._remote_names(root, source)

            for entry in ReactRouteReader(self.context.routes).routes_in(
                root, source
            ):
                key = (entry.component, entry.route or "")

                if key in seen:
                    continue

                seen.add(key)

                # `lazy: () => import("remote/Pagina")` aponta direto
                # para o módulo; nas outras formas é o nome local.
                provider, exposed = (
                    specifiers.split(entry.specifier, self.catalog)
                    if entry.specifier
                    else remote_of.get(entry.component, (None, ""))
                )

                if provider:
                    # A tela é de quem publica o módulo, mesmo que a
                    # rota esteja declarada no roteador de quem hospeda.
                    file = self._exposed_file(provider, exposed)

                else:
                    # O arquivo da tela é o do COMPONENTE, não o do
                    # roteador. Apontar para o roteador faz toda tela
                    # alcançar tudo que ele importa, e a atribuição de
                    # fragmento a tela vira ruído: cada tela recebe as
                    # dependências de todas as outras.
                    target = (
                        ModuleResolver.resolve(entry.specifier, file_path)
                        if entry.specifier
                        else imports.file_for(entry.component)
                    )

                    file = (
                        self.context.relative(target)
                        if target
                        else self.context.relative(file_path)
                    )

                found.append(
                    Screen(
                        component=entry.component,
                        microfrontend=provider or owner,
                        route=entry.route,
                        route_expression=entry.expression,
                        file=file,
                        line=entry.line,
                    )
                )

        return found
