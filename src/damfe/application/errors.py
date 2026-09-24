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
