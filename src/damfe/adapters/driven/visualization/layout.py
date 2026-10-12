"""
Posicionamento dos nós e geometria das arestas.

O layout é calculado aqui, em Python, e não no navegador: o mesmo
conjunto de artefatos produz sempre o mesmo desenho, e o HTML
resultante não depende de rede nem de JavaScript para renderizar.

Três arranjos, um por tipo de pergunta:

- `force`: micro frontends ligados por relações entre pares. Cada
  componente conexo é arranjado à parte, por força dirigida, e os
  componentes são empacotados lado a lado. O círculo fixo de antes
  sobrepunha os nós a partir de umas vinte unidades e cruzava todas
  as arestas no meio.
- `bipartite`: micro frontends de um lado, o que eles compartilham
  (chave de estado, endpoint) do outro. Acoplamento de muitos com
  muitos vira uma aresta por participante, não uma por par.
- `clusters`: telas e fragmentos agrupados pelo micro frontend dono.

Tudo é determinístico sem semente: a posição inicial vem da ordem
dos identificadores, e o número de iterações é fixo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


#: Altura de um nó de micro frontend: nome e uma linha de contagem.
NODE_HEIGHT = 40

#: Altura de uma linha nas listas (bipartido e grupos).
ROW_HEIGHT = 30

#: Folga entre caixas, que a remoção de sobreposição garante.
GAP = 22

#: Margem em volta do desenho.
MARGIN = 32


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class Box:
    """Um nó desenhado: centro, largura e altura."""

    x: float
    y: float
    w: float
    h: float

    @property
    def left(self) -> float:
        return self.x - self.w / 2

    @property
    def right(self) -> float:
        return self.x + self.w / 2

    @property
    def top(self) -> float:
        return self.y - self.h / 2

    @property
    def bottom(self) -> float:
        return self.y + self.h / 2

    def moved(self, dx: float, dy: float) -> "Box":
        return Box(self.x + dx, self.y + dy, self.w, self.h)


@dataclass(frozen=True)
class Frame:
    """Uma moldura de grupo: canto superior esquerdo e tamanho."""

    x: float
    y: float
    w: float
    h: float


def text_width(text: str, size: float = 12.5) -> float:
    """Largura aproximada de um texto na fonte do relatório."""

    return len(text) * size * 0.58


# ----------------------------------------------------------------------
# Força dirigida, por componente
# ----------------------------------------------------------------------


def force(
    sizes: dict[str, tuple[float, float]],
    edges: list[tuple[str, str, float]],
    width: float = 1100,
) -> tuple[dict[str, Box], list[str], float, float]:
    """
    Posições dos nós ligados, e os nós soltos à parte.

    Devolve (caixas, soltos, largura, altura). Os soltos — sem
    nenhuma aresta no recorte — não entram no arranjo: espalhados
    entre os ligados, empurrariam tudo para longe sem dizer nada.
    O desenho os põe numa faixa própria, abaixo.
    """

    neighbours: dict[str, set[str]] = {node: set() for node in sizes}

    weights: dict[tuple[str, str], float] = {}

    for source, target, weight in edges:

        if source == target or source not in sizes or target not in sizes:
            continue

        pair = (source, target) if source < target else (target, source)

        weights[pair] = weights.get(pair, 0) + weight

        neighbours[source].add(target)
        neighbours[target].add(source)

    isolated = sorted(node for node, linked in neighbours.items() if not linked)

    components = _components(neighbours, set(isolated))

    placed = [
        _relaxed(component, sizes, weights)
        for component in components
    ]

    boxes, used_width, used_height = _pack(placed, width)

    return boxes, isolated, used_width, used_height


def _components(neighbours: dict[str, set[str]], skip: set[str]) -> list[list[str]]:
    """Componentes conexos, os maiores primeiro."""

    seen: set[str] = set(skip)

    found: list[list[str]] = []

    for start in sorted(neighbours):

        if start in seen:
            continue

        stack = [start]
        component = []

        seen.add(start)

        while stack:

            node = stack.pop()
            component.append(node)

            for other in sorted(neighbours[node]):
                if other not in seen:
                    seen.add(other)
                    stack.append(other)

        found.append(sorted(component))

    return sorted(found, key=lambda item: (-len(item), item[0]))


def _relaxed(
    nodes: list[str],
    sizes: dict[str, tuple[float, float]],
    weights: dict[tuple[str, str], float],
) -> dict[str, Box]:
    """
    Fruchterman-Reingold sobre um componente, e depois sem sobreposição.

    A distância ideal acompanha a largura média dos rótulos: nomes
    de micro frontend são longos, e uma distância pensada para
    círculos colava as caixas.
    """

    count = len(nodes)

    if count == 1:
        width, height = sizes[nodes[0]]
        return {nodes[0]: Box(0, 0, width, height)}

    mean = sum(sizes[node][0] for node in nodes) / count

    ideal = max(mean * 0.75, 100) + GAP

    radius = ideal * math.sqrt(count) * 0.8

    position = {
        node: [
            radius * math.cos(2 * math.pi * index / count),
            radius * math.sin(2 * math.pi * index / count),
        ]
        for index, node in enumerate(nodes)
    }

    links = [
        (source, target, weight)
        for (source, target), weight in sorted(weights.items())
        if source in position and target in position
    ]

    iterations = 260

    temperature = radius

    for step in range(iterations):

        shift = {node: [0.0, 0.0] for node in nodes}

        for index, first in enumerate(nodes):

            for second in nodes[index + 1:]:

                dx = position[first][0] - position[second][0]
                dy = position[first][1] - position[second][1]

                distance = math.hypot(dx, dy) or 0.01

                push = ideal * ideal / distance

                shift[first][0] += dx / distance * push
                shift[first][1] += dy / distance * push
                shift[second][0] -= dx / distance * push
                shift[second][1] -= dy / distance * push

        for source, target, weight in links:

            dx = position[source][0] - position[target][0]
            dy = position[source][1] - position[target][1]

            distance = math.hypot(dx, dy) or 0.01

            pull = distance * distance / ideal * min(weight, 3)

            shift[source][0] -= dx / distance * pull
            shift[source][1] -= dy / distance * pull
            shift[target][0] += dx / distance * pull
            shift[target][1] += dy / distance * pull

        # Um pouco de gravidade: componente com hub não espalha as
        # folhas até o infinito.
        for node in nodes:
            shift[node][0] -= position[node][0] * 0.08
            shift[node][1] -= position[node][1] * 0.08

        limit = temperature * (1 - step / iterations) + 1

        for node in nodes:

            dx, dy = shift[node]

            length = math.hypot(dx, dy) or 0.01

            factor = min(length, limit) / length

            position[node][0] += dx * factor
            position[node][1] += dy * factor

    # Paisagem: a tela é mais larga que alta, e um arranjo redondo
    # deixaria as laterais vazias enquanto aperta os rótulos, que são
    # largos. Estica na horizontal antes de separar.
    xs = [position[node][0] for node in nodes]
    ys = [position[node][1] for node in nodes]

    span_x = (max(xs) - min(xs)) or 1
    span_y = (max(ys) - min(ys)) or 1

    stretch = min(max(1.7 * span_y / span_x, 1.0), 2.2)

    boxes = {
        node: Box(position[node][0] * stretch, position[node][1], *sizes[node])
        for node in nodes
    }

    # Folga larga entre nós ligados: com a folga mínima, dois vizinhos
    # encostados deixam a aresta entre eles do tamanho da seta.
    return separate(boxes, gap=GAP * 3)


def separate(boxes: dict[str, Box], passes: int = 120, gap: float = GAP) -> dict[str, Box]:
    """
    Afasta as caixas que se sobrepõem, pelo eixo de menor sobreposição.

    A força dirigida trata nós como pontos; rótulos longos ainda
    encostam. Empurrar pelo eixo mais curto mexe o mínimo no
    arranjo que a força encontrou.
    """

    current = dict(boxes)

    names = sorted(current)

    for _ in range(passes):

        moved = False

        for index, first in enumerate(names):

            for second in names[index + 1:]:

                a = current[first]
                b = current[second]

                overlap_x = (a.w + b.w) / 2 + gap - abs(a.x - b.x)
                overlap_y = (a.h + b.h) / 2 + gap - abs(a.y - b.y)

                if overlap_x <= 0 or overlap_y <= 0:
                    continue

                moved = True

                if overlap_x < overlap_y:
                    direction = 1 if a.x >= b.x else -1
                    current[first] = a.moved(direction * overlap_x / 2, 0)
                    current[second] = b.moved(-direction * overlap_x / 2, 0)
                else:
                    direction = 1 if a.y >= b.y else -1
                    current[first] = a.moved(0, direction * overlap_y / 2)
                    current[second] = b.moved(0, -direction * overlap_y / 2)

        if not moved:
            break

    return current


def _pack(
    components: list[dict[str, Box]],
    width: float,
) -> tuple[dict[str, Box], float, float]:
    """Componentes em prateleiras, da esquerda para a direita."""

    placed: dict[str, Box] = {}

    cursor_x = MARGIN
    cursor_y = MARGIN
    shelf = 0.0
    used = 0.0

    for component in components:

        left = min(box.left for box in component.values())
        top = min(box.top for box in component.values())
        right = max(box.right for box in component.values())
        bottom = max(box.bottom for box in component.values())

        span_x = right - left
        span_y = bottom - top

        if cursor_x > MARGIN and cursor_x + span_x > width - MARGIN:
            cursor_x = MARGIN
            cursor_y += shelf + GAP * 2
            shelf = 0.0

        for node, box in component.items():
            placed[node] = box.moved(cursor_x - left, cursor_y - top)

        cursor_x += span_x + GAP * 3
        shelf = max(shelf, span_y)
        used = max(used, cursor_x)

    height = cursor_y + shelf + MARGIN if components else 0.0

    return placed, used, height


def grid(
    nodes: list[str],
    sizes: dict[str, tuple[float, float]],
    top: float,
    width: float,
) -> tuple[dict[str, Box], float]:
    """Nós soltos em linhas, a partir de `top`. Devolve as caixas e a altura."""

    boxes: dict[str, Box] = {}

    x = MARGIN
    y = top
    row = 0.0

    for node in nodes:

        w, h = sizes[node]

        if x > MARGIN and x + w > width - MARGIN:
            x = MARGIN
            y += row + GAP
            row = 0.0

        boxes[node] = Box(x + w / 2, y + h / 2, w, h)

        x += w + GAP
        row = max(row, h)

    return boxes, (y + row - top) if nodes else 0.0


# ----------------------------------------------------------------------
# Bipartido
# ----------------------------------------------------------------------


def bipartite(
    left: dict[str, tuple[float, float]],
    right: dict[str, tuple[float, float]],
    edges: list[tuple[str, str]],
    gap: float = 320,
) -> tuple[dict[str, Box], float, float]:
    """
    Duas colunas, ordenadas para cruzar o mínimo.

    A ordem é a heurística do baricentro: cada lado se ordena pela
    posição média dos vizinhos no outro, alternando, algumas vezes.
    """

    order_left = sorted(left)
    order_right = sorted(right)

    linked_left: dict[str, list[str]] = {node: [] for node in left}
    linked_right: dict[str, list[str]] = {node: [] for node in right}

    for source, target in edges:

        if source in left and target in right:
            linked_left[source].append(target)
            linked_right[target].append(source)

    def barycenter(nodes: list[str], linked: dict, other: list[str]) -> list[str]:

        rank = {node: index for index, node in enumerate(other)}

        def key(node: str) -> tuple[float, str]:
            ranks = [rank[item] for item in linked[node] if item in rank]
            return (sum(ranks) / len(ranks) if ranks else len(other), node)

        return sorted(nodes, key=key)

    for _ in range(8):
        order_right = barycenter(order_right, linked_right, order_left)
        order_left = barycenter(order_left, linked_left, order_right)

    rows = max(len(order_left), len(order_right), 1)

    height = MARGIN * 2 + rows * ROW_HEIGHT

    left_width = max((size[0] for size in left.values()), default=0)
    right_width = max((size[0] for size in right.values()), default=0)

    left_x = MARGIN + left_width / 2
    right_x = MARGIN + left_width + gap + right_width / 2

    boxes: dict[str, Box] = {}

    for order, sizes, x in (
        (order_left, left, left_x),
        (order_right, right, right_x),
    ):

        # A coluna mais curta se espalha pela altura da mais longa:
        # alinhada ao topo, as arestas desceriam todas em diagonal.
        step = (rows * ROW_HEIGHT) / max(len(order), 1)

        for index, node in enumerate(order):
            boxes[node] = Box(x, MARGIN + step * (index + 0.5), *sizes[node])

    width = MARGIN * 2 + left_width + gap + right_width

    return boxes, width, height


# ----------------------------------------------------------------------
# Grupos
# ----------------------------------------------------------------------


@dataclass
class Group:
    """Um grupo de nós com título, desenhado como moldura."""

    id: str
    title_width: float
    members: list[tuple[str, float]]


def clusters(
    groups: list[Group],
    edges: list[tuple[str, str]],
    owner: dict[str, str],
) -> tuple[dict[str, Box], dict[str, Frame], float, float]:
    """
    Grupos em camadas, da esquerda para a direita, no sentido do fluxo.

    Quem publica, navega ou instancia fica à esquerda de quem
    recebe, e as arestas correm para a direita sem atravessar
    moldura. A camada é o caminho mais longo desde uma origem;
    ciclos são quebrados pela primeira aresta que fecha a volta,
    numa ordem fixa. Dentro de cada camada, a ordem é a do
    baricentro dos predecessores, que encurta e descruza as arestas.
    """

    if not groups:
        return {}, {}, 0.0, 0.0

    names = sorted(group.id for group in groups)

    following: dict[str, set[str]] = {name: set() for name in names}

    for source, target in edges:

        a, b = owner.get(source), owner.get(target)

        if a in following and b in following and a != b:
            following[a].add(b)

    preceding: dict[str, set[str]] = {name: set() for name in names}

    for name in names:
        for other in following[name]:
            preceding[other].add(name)

    # Quebra de ciclos por busca em profundidade: começa por quem
    # mais emite do que recebe, que é o jeito de uma origem.
    start = sorted(
        names,
        key=lambda name: (-(len(following[name]) - len(preceding[name])), name),
    )

    kept: dict[str, set[str]] = {name: set() for name in names}

    visiting: set[str] = set()
    done: set[str] = set()

    def visit(name: str) -> None:

        visiting.add(name)

        for other in sorted(following[name]):

            if other in visiting:
                continue

            kept[name].add(other)

            if other not in done:
                visit(other)

        visiting.discard(name)
        done.add(name)

    for name in start:
        if name not in done:
            visit(name)

    layer: dict[str, int] = {name: 0 for name in names}

    for _ in range(len(names)):

        changed = False

        for name in names:
            for other in kept[name]:
                if layer[other] < layer[name] + 1:
                    layer[other] = layer[name] + 1
                    changed = True

        if not changed:
            break

    columns: dict[int, list[str]] = {}

    for name in names:
        columns.setdefault(layer[name], []).append(name)

    rank: dict[str, float] = {}

    for index in sorted(columns):

        def key(name: str) -> tuple[float, str]:
            ranks = [rank[item] for item in preceding[name] if item in rank]
            return (sum(ranks) / len(ranks) if ranks else math.inf, name)

        columns[index] = sorted(columns[index], key=key)

        for position, name in enumerate(columns[index]):
            rank[name] = position

    padding = 14
    header = 34

    by_id = {group.id: group for group in groups}

    size: dict[str, tuple[float, float]] = {}

    for name in names:

        group = by_id[name]

        inner = max([group.title_width] + [w for _, w in group.members])

        size[name] = (
            inner + padding * 2,
            header + len(group.members) * ROW_HEIGHT + padding,
        )

    # Uma coluna por camada, mesmo longa: partida em duas, as arestas
    # que vão à segunda atravessariam as molduras da primeira. Rolar
    # na vertical custa menos que ler através de caixas.
    stacks = [columns[index] for index in sorted(columns)]

    heights = [
        sum(size[name][1] for name in stack) + GAP * 2 * (len(stack) - 1)
        for stack in stacks
    ]

    tallest = max(heights)

    boxes: dict[str, Box] = {}
    frames: dict[str, Frame] = {}

    x = MARGIN

    for stack, stack_height in zip(stacks, heights):

        column_width = max(size[name][0] for name in stack)

        # Coluna mais baixa centrada na mais alta.
        y = MARGIN + (tallest - stack_height) / 2

        for name in stack:

            frame_width, frame_height = size[name]

            frames[name] = Frame(x, y, frame_width, frame_height)

            for row, (member, member_width) in enumerate(by_id[name].members):
                boxes[member] = Box(
                    x + padding + member_width / 2,
                    y + header + row * ROW_HEIGHT + ROW_HEIGHT / 2 - 2,
                    member_width,
                    ROW_HEIGHT - 8,
                )

            y += frame_height + GAP * 2

        x += column_width + 150

    return boxes, frames, x - 150 + MARGIN, MARGIN * 2 + tallest


# ----------------------------------------------------------------------
# Arestas
# ----------------------------------------------------------------------


def border(box: Box, toward: Point, offset: float = 4) -> Point:
    """Onde a reta do centro da caixa até `toward` cruza a borda dela."""

    dx = toward.x - box.x
    dy = toward.y - box.y

    if dx == 0 and dy == 0:
        return Point(box.x, box.y)

    scale_x = (box.w / 2 + offset) / abs(dx) if dx else math.inf
    scale_y = (box.h / 2 + offset) / abs(dy) if dy else math.inf

    scale = min(scale_x, scale_y)

    return Point(box.x + dx * scale, box.y + dy * scale)


def link(start: Box, end: Box, bow: float = 0.0) -> str:
    """
    Caminho SVG entre duas caixas, de borda a borda.

    A curvatura separa as relações diferentes do mesmo par, que de
    outro modo cairiam uma em cima da outra.
    """

    middle = Point((start.x + end.x) / 2, (start.y + end.y) / 2)

    dx = end.x - start.x
    dy = end.y - start.y

    control = Point(middle.x - dy * bow, middle.y + dx * bow)

    first = border(start, control)
    last = border(end, control)

    return (
        f"M {first.x:.1f} {first.y:.1f} "
        f"Q {control.x:.1f} {control.y:.1f} "
        f"{last.x:.1f} {last.y:.1f}"
    )


def sideways(start: Box, end: Box, same_column: bool = False) -> str:
    """
    Curva em S entre colunas: sai pela lateral de uma caixa e entra
    pela lateral da outra. Na mesma coluna, contorna pela direita.
    """

    if same_column:

        x = max(start.right, end.right) + 6
        reach = x + 30 + abs(end.y - start.y) * 0.12

        return (
            f"M {start.right + 4:.1f} {start.y:.1f} "
            f"C {reach:.1f} {start.y:.1f} {reach:.1f} {end.y:.1f} "
            f"{end.right + 4:.1f} {end.y:.1f}"
        )

    forward = end.x > start.x

    x1 = start.right + 4 if forward else start.left - 4
    x2 = end.left - 4 if forward else end.right + 4

    bend = max(abs(x2 - x1) * 0.5, 40) * (1 if forward else -1)

    return (
        f"M {x1:.1f} {start.y:.1f} "
        f"C {x1 + bend:.1f} {start.y:.1f} {x2 - bend:.1f} {end.y:.1f} "
        f"{x2:.1f} {end.y:.1f}"
    )
