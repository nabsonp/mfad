"""Application failures, independent of how they will be displayed."""

from __future__ import annotations


class ApplicationError(Exception):
    """Base of every expected use-case failure."""


class RepositoryNotFound(ApplicationError):

    def __init__(self, path):
        super().__init__(f"Repository not found: {path}")
        self.path = path


class ArtifactsNotFound(ApplicationError):

    def __init__(self, path):
        super().__init__(f"No artifacts found in: {path}")
        self.path = path


class UnsupportedPlatform(ApplicationError):

    def __init__(self, path, platform: str):
        super().__init__(
            f"{path} is built on {platform}, a platform with its own "
            "integration that MFAD does not reconstruct, and outside it "
            "there is no micro frontend an extractor recognizes."
        )
        self.path = path
        self.platform = platform


class NoMicroFrontends(ApplicationError):

    def __init__(self, path):
        super().__init__(
            f"The reconstruction in {path} found no micro frontend; "
            "there is nothing to detect."
        )
        self.path = path
