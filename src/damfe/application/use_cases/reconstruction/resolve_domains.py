"""
Resolver os domínios declarados contra os artefatos extraídos.

Não é extração: não lê código, não usa tree-sitter e não conhece
nenhuma tecnologia de micro frontend. É o cruzamento entre uma
declaração do usuário e artefatos que já existem — e por isso mora
na camada de aplicação, não num adaptador.
"""

from __future__ import annotations

from pathlib import Path

from damfe.application.ports import SpecRepository, UseCase
from damfe.application.results import DomainsResult
from damfe.domain import ArtifactSet, Domain


class ResolveDomainsUseCase(UseCase[DomainsResult]):

    def __init__(
        self,
        spec_path: Path,
        specs: SpecRepository,
        artifacts: ArtifactSet | None = None,
    ):
        self.spec_path = spec_path
        self.specs = specs
        self.artifacts = artifacts

    def execute(self) -> DomainsResult:

        mapa = self.specs.load_domains(self.spec_path)

        artifacts = self.artifacts

        if not mapa or artifacts is None:
            return DomainsResult(domains=[], declared=bool(mapa))

        domains = {
            declaration.name: Domain(
                name=declaration.name,
                routes=declaration.routes,
                endpoints=declaration.endpoints,
                subdomains=declaration.subdomains,
            )
            for declaration in mapa.declarations
        }

        members: dict[str, set[str]] = {name: set() for name in domains}

        for microfrontend in artifacts.microfrontends:

            for screen in microfrontend.screens:

                name = mapa.of_route(screen.route or "")

                if not name:
                    continue

                domains[name].screens.append(screen.id)
                members[name].add(microfrontend.id)

        for call in artifacts.api_calls:

            name = mapa.of_endpoint(call.path)

            if not name:
                continue

            if call.path not in domains[name].api_calls:
                domains[name].api_calls.append(call.path)

            members[name].add(call.microfrontend)

        for name, owners in members.items():
            domains[name].microfrontends = sorted(owners)

        return DomainsResult(
            domains=[domains[name] for name in domains],
            declared=True,
        )
