"""
Feature listing, to serve as input to an assistant.

It is not a visualization for a human to read end to end: it is a
structured summary of the system, compact enough to fit in a prompt
and concrete enough to anchor judgment.

The unit is the SCREEN, because it is what the system's user asks
for: it has a route, composes fragments and depends on data. The name
alone would say little; the route plus the endpoints say a lot.

The destination of this is the definition of business domains, a
question static analysis does not answer on its own, because a domain
is knowledge external to the repository.
"""

from __future__ import annotations

from mfad.adapters.driven.visualization import payload
from mfad.application.ports import Renderer
from mfad.domain import AntiPatternDetection, MicroFrontendArchitecture


class FeaturesRenderer(Renderer):

    name = "features"

    extension = "md"

    def render(
        self,
        architecture: MicroFrontendArchitecture,
        detections: list[AntiPatternDetection] | None = None,
    ) -> str:

        lines = [
            f"# Features of {architecture.project or 'project'}",
            "",
            "Extracted by static analysis. One section per micro "
            "frontend, with the screens it serves, the fragments "
            "it exposes and consumes, the services it calls and the "
            "global state it reads.",
            "",
        ]

        hosted = self._hosted_fragments(architecture)

        for microfrontend in architecture.microfrontends:

            lines.extend(
                self._microfrontend(microfrontend, architecture, hosted)
            )

        lines.extend(self._relations(architecture))

        return "\n".join(lines).rstrip() + "\n"

    # ------------------------------------------------------------------

    @staticmethod
    def _hosted_fragments(architecture: MicroFrontendArchitecture) -> dict[str, list[str]]:
        """Foreign fragments instantiated in each file."""

        hosted: dict[str, list[str]] = {}

        for item in architecture.compositions:

            for render in item.renders:

                hosted.setdefault(render.file, []).append(
                    f"{item.fragment} (from {payload.short(item.provider)})"
                )

        return hosted

    def _microfrontend(
        self,
        microfrontend,
        architecture: MicroFrontendArchitecture,
        hosted: dict[str, list[str]],
    ) -> list[str]:

        lines = [
            f"## {microfrontend.id}",
            "",
            f"- own routes: `{', '.join(microfrontend.routes) or '—'}`",
            f"- role: {microfrontend.role}",
            f"- size: {microfrontend.size.code_lines} lines in "
            f"{microfrontend.size.files} files",
            "",
        ]

        if microfrontend.screens:

            lines.append("### Screens")
            lines.append("")

            for screen in microfrontend.screens:

                lines.append(f"- **{screen.component}**")

                if screen.route:
                    lines.append(f"  - route: `{screen.route}`")

                composed = hosted.get(screen.file or "", [])

                if composed:
                    lines.append(
                        f"  - composes: {', '.join(composed)}"
                    )

            lines.append("")

        if microfrontend.fragments:

            lines.append("### Exposed fragments")
            lines.append("")
            lines.extend(
                f"- `{fragment.name}`"
                for fragment in microfrontend.fragments
            )
            lines.append("")

        endpoints = sorted(
            {
                f"{call.method} {call.path}"
                for call in architecture.api_calls
                if call.microfrontend == microfrontend.id
            }
        )

        if endpoints:

            lines.append("### Called services")
            lines.append("")
            lines.append(
                "> Attributed to the micro frontend, not to the screen: "
                "calls usually live in a service module shared "
                "internally."
            )
            lines.append("")
            lines.extend(f"- `{endpoint}`" for endpoint in endpoints)
            lines.append("")

        slices = sorted(
            {
                f"{access.library}:{access.path}"
                for access in architecture.state_accesses
                if access.microfrontend == microfrontend.id
            }
        )

        if slices:

            lines.append("### Accessed global state")
            lines.append("")
            lines.extend(f"- `{item}`" for item in slices)
            lines.append("")

        return lines

    @staticmethod
    def _relations(architecture: MicroFrontendArchitecture) -> list[str]:
        """
        The edges, so the assistant sees the flow between the parts,
        and not only the content of each one.
        """

        lines = ["## Relations between micro frontends", ""]

        rows = [
            ("composition", item.consumer, item.provider, item.fragment)
            for item in architecture.compositions
        ] + [
            ("navigation", item.source, item.target, item.resolved_url or "")
            for item in architecture.navigations
        ] + [
            ("communication", item.source, item.target, item.channel)
            for item in architecture.communications
        ]

        if not rows:
            lines.append("_None._")
            return lines + [""]

        seen: set[tuple] = set()

        for relation, source, target, label in rows:

            key = (relation, source, target, label)

            if key in seen:
                continue

            seen.add(key)

            lines.append(
                f"- {payload.short(source)} → {payload.short(target)} "
                f"({relation}"
                + (f": `{label}`" if label else "")
                + ")"
            )

        return lines + [""]
