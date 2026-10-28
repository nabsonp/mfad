"""
Use cases, grouped by the three CLI modules.

Each subfolder corresponds to a module and mirrors the driven adapter
of the same name in `adapters/driven`.
"""

from mfad.application.use_cases.antipatterns import DetectUseCase
from mfad.application.use_cases.reconstruction import (
    ExtractApiCallsUseCase,
    ExtractMicroFrontendsUseCase,
    ExtractCommunicationsUseCase,
    ExtractCompositionsUseCase,
    ExtractNavigationsUseCase,
    ExtractStateAccessesUseCase,
    ReconstructUseCase,
    SetupCommunicationUseCase,
)
from mfad.application.use_cases.visualization import VisualizeUseCase

__all__ = [
    "DetectUseCase",
    "ExtractApiCallsUseCase",
    "ExtractMicroFrontendsUseCase",
    "ExtractCommunicationsUseCase",
    "ExtractCompositionsUseCase",
    "ExtractNavigationsUseCase",
    "ExtractStateAccessesUseCase",
    "ReconstructUseCase",
    "SetupCommunicationUseCase",
    "VisualizeUseCase",
]
