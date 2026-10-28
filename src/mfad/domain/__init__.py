"""
The core of the hexagon.

Pure entities: no dependency on frameworks, I/O or any micro
frontend technology. Everything else points here.
"""

from mfad.domain.communication import (
    ChannelOperation,
    edges_from_state,
    Communication,
    CommunicationSpec,
    Mechanism,
)
from mfad.domain.detection import AntiPattern, AntiPatternDetection
from mfad.domain.provenance import (
    Provenance,
    SCHEMA_VERSION,
    SourceRepository,
)
from mfad.domain.model import (
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
