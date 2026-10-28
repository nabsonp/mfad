"""
Who owns the code and who owns the route.

The two questions the navigation extraction needs to answer: which
application a file lives in, and which application owns a URL. The
second comes from `activeWhen`, which is single-spa's routing
contract.
"""

from __future__ import annotations

from pathlib import Path

from mfad.domain import MicroFrontend


class Ownership:

    def __init__(self, repository: Path, microfrontends: list[MicroFrontend]):

        self.repository = repository

        self.by_directory = {
            microfrontend.directory: microfrontend.id
            for microfrontend in microfrontends
            if microfrontend.directory
        }

        #: (route prefix, application), from the longest to the shortest
        self.routes = sorted(
            (
                (route, microfrontend.id)
                for microfrontend in microfrontends
                for route in microfrontend.routes
            ),
            key=lambda item: len(item[0]),
            reverse=True,
        )

        #: (screen route, application): the internal routes, for when
        #: no `activeWhen` says whose the URL is
        self.screens = [
            (screen.route, microfrontend.id)
            for microfrontend in microfrontends
            for screen in microfrontend.screens
            if screen.route and screen.route != "/" and "*" not in screen.route
        ]

    def of_file(self, file_path: Path) -> str | None:
        """
        The micro frontend whose directory contains the file, or `None`.

        The longest directory containing the file wins, with a segment
        boundary. Looking only at the first folder of the path got
        every monorepo with the units one level below (`apps/checkout`)
        wrong: the owner became `apps`, which is not a micro frontend,
        and the edge ended up with an end that does not exist.

        `None` is a legitimate answer: code outside any unit — shared
        package, tool, example — belongs to nobody, and the caller
        decides to discard it.
        """

        try:
            relative = file_path.resolve().relative_to(self.repository.resolve())
        except ValueError:
            return None

        parts = relative.parts

        for size in range(len(parts) - 1, 0, -1):

            owner = self.by_directory.get("/".join(parts[:size]))

            if owner:
                return owner

        return None

    def of_route(self, url: str) -> str | None:
        """
        The application that owns the URL.

        Matching is by prefix with a segment boundary, as in
        single-spa: `/checkout` covers `/checkout` and
        `/checkout/cards`, but not `/checkoutx`.

        The list is sorted from the longest prefix to the shortest, and
        the first one that matches wins. Without that the shell, which
        usually registers `/`, would swallow every route.
        """

        for route, microfrontend in self.routes:

            if self._matches(url, route):
                return microfrontend

        return self._of_screen(url)

    def _of_screen(self, url: str) -> str | None:
        """
        The application whose screens live at the URL, when no
        `activeWhen` matches: a system mounted without
        `registerApplication` in the code, or a target that is an
        internal route of another application (`/property/:id` inside
        the one mounted at `/property`). Only valid if a single
        application has a screen at that path.
        """

        owners = {
            microfrontend
            for route, microfrontend in self.screens
            if self._shares_path(url, route)
        }

        return owners.pop() if len(owners) == 1 else None

    @staticmethod
    def _shares_path(url: str, route: str) -> bool:
        """
        One path continues the other, segment by segment: `/property/{param}`
        and `/property/:assetId/add-boiler-house`. The first segment must
        be literal and equal in both.
        """

        received = [segment for segment in url.split("?")[0].split("#")[0].split("/") if segment]
        expected = [segment for segment in route.split("/") if segment]

        if not received or not expected or received[0] != expected[0] or expected[0].startswith(":"):
            return False

        return all(
            wanted.startswith(":") or got == "{param}" or got == wanted
            for got, wanted in zip(received, expected)
        )

    @staticmethod
    def _matches(url: str, route: str) -> bool:

        # `activeWhen: ["/"]` means "always active", not "owner of every
        # URL in the system" — it is the background layer, beneath the
        # others. Treating it as a prefix would turn any path, including
        # API URLs, into navigation to it.
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
        Route with a dynamic segment: `/users/:id/profile`.

        single-spa matches `:id` with anything within a segment, and
        does not match an empty segment. Comparing the whole route as
        text would make `/users/:id/profile` never match
        `/users/123/profile` — which is exactly what it exists to
        match.

        It is still a prefix: once the declared part matches, whatever
        comes after belongs to the same application.
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
        Route with a hash: `/pathname/#/hash`.

        single-spa requires the hash part to match in full, while the
        path before it is still a prefix.
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
