"""
Node placement and edge geometry.

The layout is computed here, in Python, not in the browser: the same
set of artifacts always produces the same drawing, and the resulting
HTML depends on neither network nor JavaScript to render.

Three arrangements, one per kind of question:

- `force`: micro frontends linked by pairwise relations. Each
  connected component is arranged separately, by force-directed
  layout, and the components are packed side by side. The fixed
  circle used before overlapped the nodes from about twenty units on
  and crossed every edge in the middle.
- `bipartite`: micro frontends on one side, what they share (state
  key, endpoint) on the other. Many-to-many coupling becomes one edge
  per participant, not one per pair.
- `clusters`: screens and fragments grouped by their owning micro
  frontend.

Everything is deterministic without a seed: the initial position
comes from the order of the identifiers, and the number of iterations
is fixed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


#: Height of a micro frontend node: name and one line of counts.
NODE_HEIGHT = 40

#: Height of a row in the lists (bipartite and groups).
ROW_HEIGHT = 30

#: Gap between boxes, guaranteed by overlap removal.
GAP = 22

#: Margin around the drawing.
MARGIN = 32


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class Box:
    """A drawn node: center, width and height."""

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
    """A group frame: top-left corner and size."""

    x: float
    y: float
    w: float
    h: float


def text_width(text: str, size: float = 12.5) -> float:
    """Approximate width of a text in the report font."""

    return len(text) * size * 0.58


# ----------------------------------------------------------------------
# Force-directed, per component
# ----------------------------------------------------------------------


def force(
    sizes: dict[str, tuple[float, float]],
    edges: list[tuple[str, str, float]],
    width: float = 1100,
) -> tuple[dict[str, Box], list[str], float, float]:
    """
    Positions of the linked nodes, and the loose nodes apart.

    Returns (boxes, loose, width, height). The loose ones, with no
    edge at all in the slice, do not enter the arrangement: scattered
    among the linked ones, they would push everything away without
    saying anything. The drawing puts them in their own strip, below.
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
    """Connected components, largest first."""

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
    Fruchterman-Reingold over a component, then without overlap.

    The ideal distance follows the average label width: micro
    frontend names are long, and a distance meant for circles stuck
    the boxes together.
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

        # A bit of gravity: a component with a hub does not spread its
        # leaves to infinity.
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

    # Landscape: the screen is wider than tall, and a round arrangement
    # would leave the sides empty while squeezing the labels, which are
    # wide. Stretch horizontally before separating.
    xs = [position[node][0] for node in nodes]
    ys = [position[node][1] for node in nodes]

    span_x = (max(xs) - min(xs)) or 1
    span_y = (max(ys) - min(ys)) or 1

    stretch = min(max(1.7 * span_y / span_x, 1.0), 2.2)

    boxes = {
        node: Box(position[node][0] * stretch, position[node][1], *sizes[node])
        for node in nodes
    }

    # Wide gap between linked nodes: with the minimum gap, two neighbors
    # touching leave the edge between them as short as the arrow.
    return separate(boxes, gap=GAP * 3)


def separate(boxes: dict[str, Box], passes: int = 120, gap: float = GAP) -> dict[str, Box]:
    """
    Pushes overlapping boxes apart, along the axis of smallest overlap.

    Force-directed layout treats nodes as points; long labels still
    touch. Pushing along the shortest axis disturbs the arrangement
    the force found as little as possible.
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
    """Components on shelves, from left to right."""

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
    """Loose nodes in rows, starting at `top`. Returns the boxes and the height."""

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
# Bipartite
# ----------------------------------------------------------------------


def bipartite(
    left: dict[str, tuple[float, float]],
    right: dict[str, tuple[float, float]],
    edges: list[tuple[str, str]],
    gap: float = 320,
) -> tuple[dict[str, Box], float, float]:
    """
    Two columns, ordered to cross as little as possible.

    The order is the barycenter heuristic: each side is ordered by the
    mean position of its neighbors on the other, alternating, a few
    times.
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

        # The shorter column spreads over the height of the longer one:
        # aligned to the top, the edges would all go down diagonally.
        step = (rows * ROW_HEIGHT) / max(len(order), 1)

        for index, node in enumerate(order):
            boxes[node] = Box(x, MARGIN + step * (index + 0.5), *sizes[node])

    width = MARGIN * 2 + left_width + gap + right_width

    return boxes, width, height


# ----------------------------------------------------------------------
# Groups
# ----------------------------------------------------------------------


@dataclass
class Group:
    """A group of nodes with a title, drawn as a frame."""

    id: str
    title_width: float
    members: list[tuple[str, float]]


def clusters(
    groups: list[Group],
    edges: list[tuple[str, str]],
    owner: dict[str, str],
) -> tuple[dict[str, Box], dict[str, Frame], float, float]:
    """
    Groups in layers, from left to right, in the direction of the flow.

    Whoever publishes, navigates or instantiates sits to the left of
    whoever receives, and the edges run rightwards without crossing a
    frame. The layer is the longest path from a source; cycles are
    broken at the first edge that closes the loop, in a fixed order.
    Within each layer, the order is the barycenter of the
    predecessors, which shortens and uncrosses the edges.
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

    # Cycle breaking by depth-first search: starts with whoever
    # emits more than it receives, which is what a source looks like.
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

    # One column per layer, even a long one: split in two, the edges
    # going to the second would cross the frames of the first. Scrolling
    # vertically costs less than reading through boxes.
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

        # Shorter column centered on the taller one.
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
# Edges
# ----------------------------------------------------------------------


def border(box: Box, toward: Point, offset: float = 4) -> Point:
    """Where the line from the box center toward `toward` crosses its border."""

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
    SVG path between two boxes, from border to border.

    The curvature separates the different relations of the same pair,
    which would otherwise fall on top of one another.
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
    S-curve between columns: leaves through the side of one box and
    enters through the side of the other. In the same column, it goes
    around on the right.
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
