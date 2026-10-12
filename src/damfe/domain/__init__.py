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
from damfe.domain.detection import AntiPattern, AntiPatternDetection
from damfe.domain.provenance import (
    Provenance,
    SCHEMA_VERSION,
    SourceRepository,
)
from damfe.domain.model import (
    ApiCall,
    CodeSize,
    Endpoint,
    MicroFrontend,
    MicroFrontendArchitecture,
    Fragment,
    Composition,
    Navigation,
    Placement,
    RenderLocation,
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
    "Endpoint",
    "CommunicationSpec",
    "MicroFrontendArchitecture",
    "AntiPattern",
    "AntiPatternDetection",
    "Fragment",
    "Composition",
    "Mechanism",
    "Navigation",
    "Placement",
    "Provenance",
    "RenderLocation",
    "SCHEMA_VERSION",
    "Screen",
    "SourceLocation",
    "SourceRepository",
    "StateAccess",
]
