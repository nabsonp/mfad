"""
Leitores de roteamento.

Eixo distinto do de integração. single-spa e Module Federation
dizem como as unidades viram um sistema; React Router, Angular
Router e Vue Router dizem como UMA unidade declara suas telas, e
qualquer combinação dos dois existe: single-spa com Angular,
Module Federation com React.

Um leitor por tecnologia de roteamento, usado pelos reconstrutores
dos dois eixos.
"""

from mfad.adapters.driven.reconstruction.routers.angular import (
    AngularRouteReader,
)

from mfad.adapters.driven.reconstruction.routers.react import (
    ReactRouteReader,
    RouteEntry,
)

__all__ = ["AngularRouteReader", "ReactRouteReader", "RouteEntry"]
