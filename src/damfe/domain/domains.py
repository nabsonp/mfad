"""
Domínios de negócio: a declaração e o artefato.

Domínio não está no código. É conhecimento do negócio, declarado
pelo usuário em `.damfe/domains.yml` e resolvido contra os
artefatos extraídos — como o mecanismo de comunicação, e pelo
mesmo motivo.

A hierarquia existe para tornar as regras robustas à granularidade.
Chamar `carrinho`, `pagamento` e `entrega` de três domínios ou de
três subdomínios de `pedidos` é escolha de quem declara, e não
deveria mudar o veredito sobre o micro frontend que serve os três.
Por isso **as regras operam no nível de topo**: subdomínio é
registro, não divisão.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DomainDeclaration:
    """Um domínio como o usuário o declarou."""

    name: str
    routes: list[str] = field(default_factory=list)
    endpoints: list[str] = field(default_factory=list)
    subdomains: list[str] = field(default_factory=list)


@dataclass
class DomainMap:
    """O mapa declarado. Vazio significa que não houve declaração."""

    declarations: list[DomainDeclaration] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.declarations)

    def of_route(self, route: str) -> str | None:
        return self._match(route, lambda item: item.routes)

    def of_endpoint(self, path: str) -> str | None:
        return self._match(path, lambda item: item.endpoints)

    def _match(self, value: str, select) -> str | None:
        """
        Prefixo mais longo vence, com fronteira de segmento.

        Mesma regra do `activeWhen`, inclusive na exceção: `/` casa
        apenas o caminho exato. Um domínio declarado com `/` senão
        engoliria o sistema inteiro — erro que modelos de linguagem
        cometem com frequência ao propor o mapa.
        """

        if not value:
            return None

        best, length = None, -1

        for declaration in self.declarations:

            for prefix in select(declaration):

                if not self._covers(value, prefix):
                    continue

                if len(prefix) > length:
                    best, length = declaration.name, len(prefix)

        return best

    @staticmethod
    def _covers(value: str, prefix: str) -> bool:

        if prefix == "/":
            return value == "/"

        if not value.startswith(prefix):
            return False

        rest = value[len(prefix):]

        return rest == "" or rest[0] in "/?"


@dataclass
class Domain:
    """
    Um domínio com seus membros resolvidos.

    `microfrontends` é o campo que faz as regras funcionarem: é ele
    que expõe o cruzamento entre a decomposição por domínio e a
    decomposição em micro frontends.
    """

    name: str
    routes: list[str] = field(default_factory=list)
    endpoints: list[str] = field(default_factory=list)
    subdomains: list[str] = field(default_factory=list)
    screens: list[str] = field(default_factory=list)
    api_calls: list[str] = field(default_factory=list)
    microfrontends: list[str] = field(default_factory=list)
