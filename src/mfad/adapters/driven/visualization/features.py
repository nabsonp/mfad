"""
Listagem de features, para servir de entrada a um assistente.

Não é visualização para humano ler de ponta a ponta: é uma
sumarização estruturada do sistema, compacta o bastante para caber
num prompt e concreta o bastante para ancorar julgamento.

A unidade é a TELA, porque ela é o que o usuário do sistema pede:
tem uma rota, compõe fragmentos e depende de dados. O nome sozinho
diria pouco; a rota mais os endpoints dizem muito.

O destino disto é a definição de domínios de negócio — pergunta
que a análise estática não responde sozinha, porque domínio é
conhecimento externo ao repositório.
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
            f"# Features de {architecture.project or 'projeto'}",
            "",
            "Extraído por análise estática. Uma seção por micro "
            "frontend, com as telas que ele serve, os fragmentos "
            "que expõe e consome, os serviços que chama e o estado "
            "global que lê.",
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
        """Fragmentos de fora instanciados em cada arquivo."""

        hosted: dict[str, list[str]] = {}

        for item in architecture.compositions:

            for render in item.renders:

                hosted.setdefault(render.file, []).append(
                    f"{item.fragment} (de {payload.short(item.provider)})"
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
            f"- rotas próprias: `{', '.join(microfrontend.routes) or '—'}`",
            f"- papel: {microfrontend.role}",
            f"- tamanho: {microfrontend.size.code_lines} linhas em "
            f"{microfrontend.size.files} arquivos",
            "",
        ]

        if microfrontend.screens:

            lines.append("### Telas")
            lines.append("")

            for screen in microfrontend.screens:

                lines.append(f"- **{screen.component}**")

                if screen.route:
                    lines.append(f"  - rota: `{screen.route}`")

                composed = hosted.get(screen.file or "", [])

                if composed:
                    lines.append(
                        f"  - compõe: {', '.join(composed)}"
                    )

            lines.append("")

        if microfrontend.fragments:

            lines.append("### Fragmentos expostos")
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

            lines.append("### Serviços chamados")
            lines.append("")
            lines.append(
                "> Atribuídos ao micro frontend, não à tela: as "
                "chamadas costumam viver num módulo de serviço "
                "compartilhado internamente."
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

            lines.append("### Estado global acessado")
            lines.append("")
            lines.extend(f"- `{item}`" for item in slices)
            lines.append("")

        return lines

    @staticmethod
    def _relations(architecture: MicroFrontendArchitecture) -> list[str]:
        """
        As arestas, para que o assistente veja o fluxo entre as
        partes — e não só o conteúdo de cada uma.
        """

        lines = ["## Relações entre micro frontends", ""]

        rows = [
            ("composição", item.consumer, item.provider, item.fragment)
            for item in architecture.compositions
        ] + [
            ("navegação", item.source, item.target, item.resolved_url or "")
            for item in architecture.navigations
        ] + [
            ("comunicação", item.source, item.target, item.channel)
            for item in architecture.communications
        ]

        if not rows:
            lines.append("_Nenhuma._")
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
