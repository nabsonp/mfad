"""
Screen that aggregates fragments from several micro frontends.

Such a screen becomes a convergence point: a failure, a contract
change or an outage in any of the providers shows up there. And
whoever maintains the screen has to keep up with the evolution of
all of them.

The signal is the number of DISTINCT FRAGMENTS the screen mounts,
not the number of providers (see `min_fragments`) nor of
instantiations: the same fragment repeated in a list is a single
dependency, however many times it appears.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mfad.adapters.driven import i18n
from mfad.application.ports import Rule
from mfad.domain import AntiPattern, AntiPatternDetection, MicroFrontendArchitecture, SourceLocation


@dataclass
class Host:
    """What a screen hosts from outside."""

    screen: str
    owner: str
    providers: set[str] = field(default_factory=set)
    fragments: list[str] = field(default_factory=list)
    locations: list[SourceLocation] = field(default_factory=list)


class HubLikeDependency(Rule):

    anti_pattern = AntiPattern(
        name="hub-like-dependency",
        description=(
            "Screen that renders many fragments, concentrating "
            "dependencies in a single point."
        ),
        category="Inter-frontend",
        reference="https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Hub-like%20Dependency",
    )

    def __init__(self, min_fragments: int = 5):

        #: Number of fragments from which the screen is considered a
        #: hub.
        #:
        #: The count is of FRAGMENTS, not of provider micro frontends.
        #: It is the number of pieces the screen has to mount that
        #: makes it a convergence point — five fragments from a single
        #: provider concentrate as much contract change as five from
        #: five.
        #:
        #: Counting distinct providers, as was done before, penalized
        #: the normal design: in an architecture with a shared
        #: component library, any screen using one of its components
        #: plus any fragment already added up to two providers and
        #: became a hub.
        self.min_fragments = min_fragments

    def check(self, architecture: MicroFrontendArchitecture) -> list[AntiPatternDetection]:

        hosts = self._hosts(architecture)

        return [
            self._detection(host)
            for host in hosts.values()
            if len(set(host.fragments)) >= self.min_fragments
        ]

    def _hosts(self, architecture: MicroFrontendArchitecture) -> dict[str, Host]:
        """
        Groups the instantiated fragments by screen.

        The link comes from the render site itself, which already
        knows on which screens it appears. It used to be by FILE — the
        screen whose file instantiates the fragment — and that broke
        when several screens are declared in the same router: the map
        kept one arbitrary screen per file, and the detection fell on
        it.
        """

        screens = {
            screen.id: screen
            for microfrontend in architecture.microfrontends
            for screen in microfrontend.screens
        }

        hosts: dict[str, Host] = {}

        for item in architecture.compositions:

            for render in item.renders:

                for identifier in render.screens:

                    screen = screens.get(identifier)

                    if not screen:
                        continue

                    host = hosts.setdefault(
                        screen.id,
                        Host(
                            screen=screen.component,
                            owner=screen.microfrontend,
                        ),
                    )

                    host.providers.add(item.provider)
                    host.fragments.append(f"{item.provider}#{item.fragment}")
                    host.locations.append(
                        SourceLocation(file=render.file, line=render.line)
                    )

        return hosts

    def _detection(self, host: Host) -> AntiPatternDetection:

        providers = sorted(host.providers)

        text = {
            "dimension": i18n.ref("dimension.composition"),
            "explanation": i18n.ref("hub.explanation"),
            "message": i18n.ref(
                "hub.message",
                screen=host.screen,
                owner=self._short(host.owner),
                fragments=len(set(host.fragments)),
                n=len(providers),
                names=", ".join(self._short(item) for item in providers),
            ),
        }

        text["facts"] = [
            i18n.fact("fact.screen", host.screen),
            i18n.fact("fact.owner", self._short(host.owner)),
            i18n.fact("fact.fragments", len(set(host.fragments))),
            i18n.fact("fact.providers", ", ".join(self._short(item) for item in providers)),
        ]

        return AntiPatternDetection(
            anti_pattern=self.name,
            dimension=i18n.t(text["dimension"]),
            explanation=i18n.t(text["explanation"]),
            message=i18n.t(text["message"]),
            subjects=[host.owner, *providers],
            locations=host.locations,
            metadata={
                "text": text,
                "edges": [
                    [host.owner, provider] for provider in providers
                ],
                "screen": host.screen,
                "providers": providers,
                "fragments": sorted(
                    {fragment.partition("#")[2] for fragment in host.fragments}
                ),
            },
        )

    @staticmethod
    def _short(name: str) -> str:

        return name.rpartition("/")[2] or name
