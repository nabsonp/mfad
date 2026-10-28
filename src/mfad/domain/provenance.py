"""
Provenance: where the artifacts came from and under which schema.

Without this a set of artifacts is anonymous — it does not say which
version of the tool produced it, nor from which revision of which
repository. For the empirical evaluation that is fatal: the result
stops being reproducible the moment the analyzed repository receives
a commit.
"""

from __future__ import annotations

from dataclasses import dataclass, field


#: Version of the artifacts' SCHEMA, not of the tool.
#:
#: Bumped when the shape of the files changes in a way that breaks
#: their readers. Kept apart from `__version__` on purpose: a bug fix
#: in the extractor changes the tool and not the schema, and during a
#: long collection one must be able to say "all results are schema
#: 1.0.0" even after switching versions midway.
SCHEMA_VERSION = "3.3.0"


@dataclass
class SourceRepository:
    """An analyzed repository, at the revision at which it was analyzed."""

    #: path relative to the analysis root. Never absolute — the
    #: artifact is versioned, and a machine path would pollute the diff.
    path: str

    #: origin URL, without credentials.
    remote: str = ""

    #: full SHA of HEAD, empty when it is not a git repository.
    commit: str = ""

    #: There were uncommitted changes at the time of the analysis. When
    #: true, `commit` does NOT identify what was read.
    dirty: bool = False


@dataclass
class Provenance:
    """The header that makes a set of artifacts self-describing."""

    schema: str = SCHEMA_VERSION
    tool: str = ""
    generated_at: str = ""
    reconstructor: str = ""
    sources: list[SourceRepository] = field(default_factory=list)

    def source(self, path: str) -> SourceRepository | None:

        for repository in self.sources:

            if repository.path == path:
                return repository

        return None
