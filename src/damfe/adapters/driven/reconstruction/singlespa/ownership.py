"""
De quem é o código e de quem é a rota.

As duas perguntas que a extração de navegação precisa responder:
em que aplicação um arquivo mora, e qual aplicação é dona de uma
URL. A segunda vem do `activeWhen`, que é o contrato de roteamento
do single-spa.
"""

from __future__ import annotations

from pathlib import Path

from damfe.domain import MicroFrontend


class Ownership:

    def __init__(self, repository: Path, microfrontends: list[MicroFrontend]):

        self.repository = repository

        self.by_directory = {
            microfrontend.directory: microfrontend.id
            for microfrontend in microfrontends
            if microfrontend.directory
        }

        #: (prefixo da rota, aplicação), do mais longo para o mais curto
        self.routes = sorted(
            (
                (route, microfrontend.id)
                for microfrontend in microfrontends
                for route in microfrontend.routes
            ),
            key=lambda item: len(item[0]),
            reverse=True,
        )

    def of_file(self, file_path: Path) -> str:

        try:
            relative = file_path.relative_to(self.repository)
        except ValueError:
            return "?"

        if not relative.parts:
            return "?"

        directory = relative.parts[0]

        return self.by_directory.get(directory, directory)

    def of_route(self, url: str) -> str | None:
        """
        A aplicação dona da URL.

        O casamento é por prefixo com fronteira de segmento, como
        no single-spa: `/checkout` cobre `/checkout` e
        `/checkout/cards`, mas não `/checkoutx`.

        A lista está ordenada do prefixo mais longo para o mais
        curto, e o primeiro que casar vence. Sem isso o shell, que
        costuma registrar `/`, engoliria todas as rotas.
        """

        for route, microfrontend in self.routes:

            if self._matches(url, route):
                return microfrontend

        return None

    @staticmethod
    def _matches(url: str, route: str) -> bool:

        # `activeWhen: ["/"]` significa "sempre ativa", não "dona de
        # toda URL do sistema" — é a camada de fundo, sob as outras.
        # Tratá-la como prefixo faria qualquer caminho, inclusive
        # URL de API, virar navegação para ela.
        if route == "/":
            return url == "/"

        if not url.startswith(route):
            return False

        rest = url[len(route):]

        return rest == "" or rest.startswith("/")
