"""Falhas da aplicação, independentes de como serão exibidas."""

from __future__ import annotations


class ApplicationError(Exception):
    """Base de toda falha prevista dos casos de uso."""


class RepositoryNotFound(ApplicationError):

    def __init__(self, path):
        super().__init__(f"Repositório não encontrado: {path}")
        self.path = path


class ArtifactsNotFound(ApplicationError):

    def __init__(self, path):
        super().__init__(f"Nenhum artefato encontrado em: {path}")
        self.path = path


class UnsupportedPlatform(ApplicationError):

    def __init__(self, path, platform: str):
        super().__init__(
            f"{path} é construído sobre {platform}, plataforma com "
            "integração própria que o MFAD não reconstrói, e fora dela "
            "não há micro frontend que um extrator reconheça."
        )
        self.path = path
        self.platform = platform


class NoMicroFrontends(ApplicationError):

    def __init__(self, path):
        super().__init__(
            f"A reconstrução em {path} não encontrou micro frontend "
            "nenhum; não há o que detectar."
        )
        self.path = path
