"""
Casos de uso, agrupados pelos três módulos do CLI.

Cada subpasta corresponde a um módulo e espelha o adaptador
conduzido de mesmo nome em `adapters/driven`.
"""

from damfe.application.use_cases.antipatterns import DetectUseCase
from damfe.application.use_cases.reconstruction import (
    ExtractApiCallsUseCase,
    ExtractMicroFrontendsUseCase,
    ExtractCommunicationsUseCase,
    ExtractCompositionsUseCase,
    ExtractNavigationsUseCase,
    ExtractStateAccessesUseCase,
    ReconstructUseCase,
    SetupCommunicationUseCase,
)
from damfe.application.use_cases.visualization import VisualizeUseCase

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
