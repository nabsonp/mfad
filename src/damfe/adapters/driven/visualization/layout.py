"""
Posicionamento dos nós e geometria das arestas.

O layout é calculado aqui, em Python, e não no navegador: o mesmo
conjunto de artefatos produz sempre o mesmo desenho, e o HTML
resultante não depende de rede nem de JavaScript para renderizar.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import networkx as nx


WIDTH = 900
HEIGHT = 560
RADIUS = 46


@dataclass(frozen=True)
class Point:
    x: float
    y: float


def positions(graph: nx.DiGraph) -> dict[str, Point]:

    return positions_for(list(graph.nodes))


def positions_for(identifiers: list[str]) -> dict[str, Point]:
    """
    Distribui os nós em círculo.

    Circular em vez de força dirigida porque é determinístico sem
    depender de semente, e legível no tamanho de sistema que a
    ferramenta encontra na prática — dezenas de nós, não milhares.
    """

    nodes = sorted(identifiers)

    if not nodes:
        return {}

    if len(nodes) == 1:
        return {nodes[0]: Point(WIDTH / 2, HEIGHT / 2)}

    center = Point(WIDTH / 2, HEIGHT / 2)

    radius = min(WIDTH, HEIGHT) / 2 - RADIUS - 40

    return {
        node: Point(
            center.x + radius * math.cos(angle),
            center.y + radius * math.sin(angle),
        )
        for node, angle in (
            (node, -math.pi / 2 + 2 * math.pi * index / len(nodes))
            for index, node in enumerate(nodes)
        )
    }


def curve(start: Point, end: Point, bow: float = 0.18) -> str:
    """
    Caminho SVG de uma aresta, curvado.

    A curvatura não é decoração: `A → B` e `B → A` existem ao mesmo
    tempo nestes grafos, e arcos opostos são a forma de distinguir
    os dois sentidos sem sobrepor um traço no outro.
    """

    trimmed_start, trimmed_end = _trim(start, end)

    middle = Point(
        (trimmed_start.x + trimmed_end.x) / 2,
        (trimmed_start.y + trimmed_end.y) / 2,
    )

    dx = trimmed_end.x - trimmed_start.x
    dy = trimmed_end.y - trimmed_start.y

    control = Point(middle.x - dy * bow, middle.y + dx * bow)

    return (
        f"M {trimmed_start.x:.1f} {trimmed_start.y:.1f} "
        f"Q {control.x:.1f} {control.y:.1f} "
        f"{trimmed_end.x:.1f} {trimmed_end.y:.1f}"
    )


def _trim(start: Point, end: Point) -> tuple[Point, Point]:
    """Encolhe a aresta para ela encostar na borda do nó, não no centro."""

    dx = end.x - start.x
    dy = end.y - start.y

    distance = math.hypot(dx, dy) or 1

    offset = RADIUS + 6

    return (
        Point(
            start.x + dx / distance * offset,
            start.y + dy / distance * offset,
        ),
        Point(
            end.x - dx / distance * offset,
            end.y - dy / distance * offset,
        ),
    )
