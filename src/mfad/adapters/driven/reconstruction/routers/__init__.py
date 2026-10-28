"""
Routing readers.

An axis separate from integration. single-spa and Module Federation
say how the units become a system; React Router, Angular Router and
Vue Router say how ONE unit declares its screens, and any combination
of the two exists: single-spa with Angular, Module Federation with
React.

One reader per routing technology, used by the reconstructors of
both axes.
"""

from mfad.adapters.driven.reconstruction.routers.angular import (
    AngularRouteReader,
)

from mfad.adapters.driven.reconstruction.routers.react import (
    ReactRouteReader,
    RouteEntry,
)

__all__ = ["AngularRouteReader", "ReactRouteReader", "RouteEntry"]
