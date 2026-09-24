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

        if ":" in route:
            return Ownership._matches_dynamic(url, route)

        if "#" in route or "#" in url:
            return Ownership._matches_hash(url, route)

        if not url.startswith(route):
            return False

        rest = url[len(route):]

        return rest == "" or rest.startswith("/")

    @staticmethod
    def _matches_dynamic(url: str, route: str) -> bool:
        """
        Rota com segmento dinâmico: `/users/:id/profile`.

        O single-spa casa `:id` com qualquer coisa dentro de um
        segmento, e não casa com segmento vazio. Comparar a rota
        inteira como texto faria `/users/:id/profile` nunca casar com
        `/users/123/profile` — que é exatamente o que ela existe para
        casar.

        Continua sendo prefixo: casada a parte declarada, o que vier
        depois pertence à mesma aplicação.
        """

        esperados = route.strip("/").split("/")
        recebidos = url.split("?")[0].split("#")[0].strip("/").split("/")

        if len(recebidos) < len(esperados):
            return False

        for esperado, recebido in zip(esperados, recebidos):

            if esperado.startswith(":"):

                if not recebido:
                    return False

                continue

            if esperado != recebido:
                return False

        return True

    @staticmethod
    def _matches_hash(url: str, route: str) -> bool:
        """
        Rota com hash: `/pathname/#/hash`.

        O single-spa exige que a parte do hash case por inteiro,
        enquanto o caminho antes dele continua sendo prefixo.
        """

        caminho_rota, _, hash_rota = route.partition("#")
        caminho_url, _, hash_url = url.partition("#")

        if hash_rota and hash_url != hash_rota:
            return False

        caminho_rota = caminho_rota.rstrip("/")

        if not caminho_rota:
            return True

        if not caminho_url.startswith(caminho_rota):
            return False

        rest = caminho_url[len(caminho_rota):]

        return rest in ("", "/") or rest.startswith("/")
