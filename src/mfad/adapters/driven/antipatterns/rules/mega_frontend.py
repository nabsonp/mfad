"""
Micro frontend far too large compared to its peers.

The catalog describes "multiple responsibilities that should be
separate". Without a domain map there is no way to state WHICH ones
they are, so what is measured is the observable consequence: the
unit grew well beyond the system's distribution.

The cut is the upper Tukey fence, on screens AND on lines of code.
Both together, not either one: many screens with little code is a
menu, a lot of code with one screen is a library.
"""

from __future__ import annotations

from mfad.adapters.driven import i18n
from mfad.adapters.driven.antipatterns.alignment import (
    Sizes,
    fences,
    peers,
)
from mfad.application.ports import Rule
from mfad.domain import AntiPattern, AntiPatternDetection, MicroFrontendArchitecture


class MegaFrontend(Rule):

    anti_pattern = AntiPattern(
        name="mega-frontend",
        description=(
            "Micro frontend much larger than its peers, concentrating "
            "responsibilities that should be separate."
        ),
        category="Intra-frontend",
        reference="https://mfe-anti-patterns.online/micro-frontends-anti-patterns/#/details/Mega%20Frontend",
    )

    def check(
        self,
        architecture: MicroFrontendArchitecture,
    ) -> list[AntiPatternDetection]:

        candidates = [
            item
            for item in peers(architecture)
            if item.metadata.get("entrypoint_resolved") is not False
        ]

        sizes = Sizes.of(candidates)

        by_screens = fences([len(item.screens) for item in candidates])
        by_lines = fences([item.size.code_lines for item in candidates])

        # Sample too small to talk about a distribution.
        if not by_screens or not by_lines:
            return []

        found: list[AntiPatternDetection] = []

        for microfrontend in candidates:

            screens = len(microfrontend.screens)
            code_lines = microfrontend.size.code_lines

            if screens <= by_screens.high or code_lines <= by_lines.high:
                continue

            text = {
                "dimension": i18n.ref("dimension.size"),
                "explanation": i18n.ref("mega.explanation"),
                "message": i18n.ref(
                    "mega.message",
                    name=self._short(microfrontend.id),
                    screens=screens,
                    lines=code_lines,
                    screen_fence=f"{by_screens.high:g}",
                    line_fence=f"{by_lines.high:g}",
                ),
            }

            text["facts"] = [
                i18n.fact("fact.screens", screens),
                i18n.fact("fact.screen_fence", f"{by_screens.high:g}"),
                i18n.fact("fact.code_lines", code_lines),
                i18n.fact("fact.line_fence", f"{by_lines.high:g}"),
            ]

            found.append(
                AntiPatternDetection(
                    anti_pattern=self.name,
                    dimension=i18n.t(text["dimension"]),
                    explanation=i18n.t(text["explanation"]),
                    message=i18n.t(text["message"]),
                    subjects=[microfrontend.id],
                    metadata={
                        "text": text,
                        "criterion": "upper outlier",
                        "screens": screens,
                        "fragments": len(microfrontend.fragments),
                        "lines": code_lines,
                        "fence_screens": by_screens.high,
                        "fence_lines": by_lines.high,
                        "median_screens": sizes.screens,
                        "median_lines": sizes.code_lines,
                    },
                )
            )

        return found

    @staticmethod
    def _short(name: str) -> str:

        return name.rpartition("/")[2] or name
