"""
Service route consumed by more than one micro frontend.

It is the coupling none of the other graphs shows. The parts do not
import each other, do not navigate to each other and exchange no
messages — and still they cannot evolve separately, because they
depend on the same backend contract. A change in the response format
breaks all of them at once, and whoever changes the service needs to
know who they all are.

Grouping is by PATH, not by path plus method: an application that
reads and another that writes the same resource share the same
contract, even if through different verbs.
"""

from __future__ import annotations

from mfad.adapters.driven import i18n
from mfad.application.ports import Rule
from mfad.domain import (
    AntiPattern,
    AntiPatternDetection,
    Endpoint,
    MicroFrontendArchitecture,
)


class HammeringApis(Rule):

    anti_pattern = AntiPattern(
        name="hammering-apis",
        description=(
            "External service route consumed by more than one micro "
            "frontend, creating a shared contract dependency."
        ),
        category="Inter-frontend",
        reference="https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Hammering%20APIs",
    )

    def __init__(self, min_callers: int = 2):

        #: Number of consumers from which the route is considered
        #: shared. Two are enough: the coupling exists from the
        #: second one on.
        self.min_callers = min_callers

    def check(self, architecture: MicroFrontendArchitecture) -> list[AntiPatternDetection]:

        return [
            self._detection(endpoint, architecture)
            for endpoint in architecture.endpoints
            if len(endpoint.microfrontends) >= self.min_callers
        ]

    def _detection(
        self,
        endpoint: Endpoint,
        architecture: MicroFrontendArchitecture,
    ) -> AntiPatternDetection:

        callers = sorted(endpoint.microfrontends)

        text = {
            "dimension": i18n.ref("dimension.shared_backend"),
            "explanation": i18n.ref("hammering.explanation"),
            "message": i18n.ref(
                "hammering.message",
                path=endpoint.path,
                n=len(callers),
                names=", ".join(self._short(caller) for caller in callers),
            ),
        }

        text["facts"] = [
            i18n.fact("fact.route", endpoint.path),
            i18n.fact("fact.callers", ", ".join(self._short(caller) for caller in callers)),
        ]

        return AntiPatternDetection(
            anti_pattern=self.name,
            dimension=i18n.t(text["dimension"]),
            explanation=i18n.t(text["explanation"]),
            message=i18n.t(text["message"]),
            subjects=callers,
            # The locations come from the calls, not from the endpoint:
            # it is the external node, and what records where the call
            # happens is the `ApiCall`.
            locations=[
                call.at
                for call in architecture.api_calls
                if call.path == endpoint.path
            ],
            metadata={
                "text": text,
                "relation": "shared_endpoint",
                # Both directions: the relation has no direction, and
                # the drawing traces one arc for each order.
                "edges": [
                    [source, target]
                    for source in callers
                    for target in callers
                    if source != target
                ],
                "path": endpoint.path,
                "methods": sorted(endpoint.methods),
                "callers": callers,
            },
        )

    @staticmethod
    def _short(name: str) -> str:

        return name.rpartition("/")[2] or name
