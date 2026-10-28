"""
Template composition readers.

Where the framework links one component to another through the
template rather than through an import, reachability needs someone to
read that link. Today only Angular works this way; in React the JSX
uses an imported identifier, and the import is enough.
"""

from mfad.adapters.driven.reconstruction.templates.angular import (
    AngularTemplates,
)

__all__ = ["AngularTemplates"]
