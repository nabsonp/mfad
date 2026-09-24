from damfe.adapters.driven.antipatterns.rules.access_to_domains import (
    AccessToDifferentDomains,
)
from damfe.adapters.driven.antipatterns.rules.cyclic_dependency import (
    CyclicDependency,
)
from damfe.adapters.driven.antipatterns.rules.global_state_communication import (
    GlobalStateCommunication,
)
from damfe.adapters.driven.antipatterns.rules.hammering_apis import (
    HammeringApis,
)
from damfe.adapters.driven.antipatterns.rules.hub_like_dependency import (
    HubLikeDependency,
)
from damfe.adapters.driven.antipatterns.rules.mega_frontend import MegaFrontend
from damfe.adapters.driven.antipatterns.rules.nano_frontend import NanoFrontend
from damfe.adapters.driven.antipatterns.rules.one_for_all import OneForAll

__all__ = [
    "AccessToDifferentDomains",
    "CyclicDependency",
    "GlobalStateCommunication",
    "HammeringApis",
    "HubLikeDependency",
    "MegaFrontend",
    "NanoFrontend",
    "OneForAll",
]
