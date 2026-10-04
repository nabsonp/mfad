"""
O núcleo do hexágono.

Entidades puras: sem dependência de framework, de I/O ou de
qualquer tecnologia de micro frontend. Tudo mais aponta para cá.
"""

from damfe.domain.communication import (
    ChannelOperation,
    edges_from_state,
    Communication,
    CommunicationSpec,
    Mechanism,
)
from damfe.domain.detection import AntiPatternDetection
from damfe.domain.provenance import (
    Provenance,
    SCHEMA_VERSION,
    SourceRepository,
)
from damfe.domain.model import (
    ApiCall,
    CodeSize,
    MicroFrontend,
    MicroFrontendArchitecture,
    Fragment,
    FragmentImport,
    Navigation,
    RenderSite,
    Screen,
    SourceLocation,
    StateAccess,
)

__all__ = [
    "edges_from_state",
    "ApiCall",
    "MicroFrontend",
    "ChannelOperation",
    "Communication",
    "CodeSize",
    "CommunicationSpec",
    "MicroFrontendArchitecture",
    "AntiPatternDetection",
    "Fragment",
    "FragmentImport",
    "Mechanism",
    "Navigation",
    "Provenance",
    "RenderSite",
    "SCHEMA_VERSION",
    "Screen",
    "SourceLocation",
    "SourceRepository",
    "StateAccess",
]
