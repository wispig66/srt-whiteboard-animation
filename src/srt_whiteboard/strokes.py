"""Low-level raster stroke extraction and pen-overlay primitives."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class Config:
    fps: int = 60
    grid_edge: int = 10
    sample_step: int = 2
    cap_long_edge: int = 1080
    brush_radius: int = 40
    ink_weight: int = 2
    color_weight: int = 1
    ink_threshold: int = 10
    ink_reveal_radius: int = 4
    target_hand_height: int = 493
    tip_anchor_x: float = 0.0
    tip_anchor_y: float = 0.0
    canvas_hex: str = "#F5EBD7"
    match_bg: bool = True
    match_bg_threshold: int = 28
    color_fill: str = "contour-wipe"
    wipe_decay: float = 0.86
    wipe_delay_ratio: float = 0.04
    wipe_blocks: int = 18
    ink_path_mode: str = "grid"
    skeleton_min_points: int = 8
    skeleton_resample_spacing: float = 2.5


def _imread_any(path: str | Path, flags: int = cv2.IMREAD_COLOR) -> np.ndarray | None:
    try:
        raw = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    return cv2.imdecode(raw, flags) if raw.size else None


def _hex_to_bgr(value: str) -> np.ndarray:
    digits = value.removeprefix("#")
    if len(digits) != 6:
        raise ValueError(f"invalid RGB color: {value}")
    try:
        red, green, blue = (int(digits[offset : offset + 2], 16) for offset in (0, 2, 4))
    except ValueError as exc:
        raise ValueError(f"invalid RGB color: {value}") from exc
    return np.array([blue, green, red], dtype=np.uint8)


def _to_grid_blocks(image: np.ndarray, edge: int) -> np.ndarray:
    height, width = image.shape[:2]
    if height % edge or width % edge:
        raise ValueError(f"image dimensions {width}x{height} are not divisible by grid edge {edge}")
    if image.ndim == 2:
        return image.reshape(height // edge, edge, width // edge, edge).transpose(0, 2, 1, 3)
    channels = image.shape[2]
    return image.reshape(
        height // edge, edge, width // edge, edge, channels
    ).transpose(0, 2, 1, 3, 4)


def _active_mask(threshold_map: np.ndarray, edge: int, threshold: int) -> np.ndarray:
    return _to_grid_blocks(threshold_map, edge).min(axis=(2, 3)) < threshold


_GRID_NEIGHBORS = [
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
]


def _walk_component(cells: set[tuple[int, int]]) -> list[tuple[int, int]]:
    remaining = set(cells)
    current = min(remaining)
    path: list[tuple[int, int]] = []
    previous_direction = (0, 1)
    while remaining:
        path.append(current)
        remaining.remove(current)
        if not remaining:
            break
        neighbors = [
            (current[0] + row, current[1] + column)
            for row, column in _GRID_NEIGHBORS
            if (current[0] + row, current[1] + column) in remaining
        ]
        if neighbors:
            def cost(
                candidate: tuple[int, int],
                origin: tuple[int, int] = current,
                incoming: tuple[int, int] = previous_direction,
            ) -> tuple[int, int, int, int]:
                degree = sum(
                    (candidate[0] + row, candidate[1] + column) in remaining
                    for row, column in _GRID_NEIGHBORS
                )
                direction = (candidate[0] - origin[0], candidate[1] - origin[1])
                turn = (
                    (direction[0] - incoming[0]) ** 2
                    + (direction[1] - incoming[1]) ** 2
                )
                return (-degree, turn, candidate[0], candidate[1])

            following = min(neighbors, key=cost)
        else:
            following = min(
                remaining,
                key=lambda candidate: (
                    (candidate[0] - current[0]) ** 2 + (candidate[1] - current[1]) ** 2,
                    candidate,
                ),
            )
        previous_direction = (following[0] - current[0], following[1] - current[1])
        current = following
    return path


def cluster_ink_streams(active: np.ndarray) -> list[list[tuple[int, int]]]:
    """Group connected active grid cells, then produce a stable path per component."""
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        active.astype(np.uint8), connectivity=8
    )
    components: list[tuple[int, int, list[tuple[int, int]]]] = []
    for label in range(1, count):
        rows, columns = np.where(labels == label)
        cells = {(int(row), int(column)) for row, column in zip(rows, columns, strict=True)}
        if not cells:
            continue
        top = int(stats[label, cv2.CC_STAT_TOP])
        left = int(stats[label, cv2.CC_STAT_LEFT])
        components.append((top, left, _walk_component(cells)))
    components.sort(key=lambda component: (component[0], component[1]))
    return [component[2] for component in components]


def flatten_streams(streams: list[list[tuple[int, int]]]) -> list[tuple[int, int]]:
    return [cell for stream in streams for cell in stream]


def _load_hand(path: Path, target_h: int) -> tuple[np.ndarray, np.ndarray] | None:
    image = _imread_any(path, cv2.IMREAD_UNCHANGED)
    if image is None:
        return None
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGRA)
    elif image.shape[2] == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)
    alpha = image[:, :, 3]
    visible_y, visible_x = np.where(alpha > 5)
    if not visible_x.size:
        return None
    left, right = int(visible_x.min()), int(visible_x.max()) + 1
    top, bottom = int(visible_y.min()), int(visible_y.max()) + 1
    cropped = image[top:bottom, left:right]
    scale = target_h / cropped.shape[0]
    width = max(1, round(cropped.shape[1] * scale))
    resized = cv2.resize(cropped, (width, target_h), interpolation=cv2.INTER_AREA)
    return resized[:, :, :3].astype(np.float32), resized[:, :, 3].astype(np.float32) / 255.0


def _procedural_tip(target_h: int) -> tuple[np.ndarray, np.ndarray]:
    height = max(36, target_h // 3)
    width = max(24, height // 3)
    bgra = np.zeros((height, width, 4), dtype=np.uint8)
    cv2.line(
        bgra,
        (width // 2, height - 1),
        (width // 2, height // 4),
        (60, 80, 120, 255),
        max(4, width // 4),
        cv2.LINE_AA,
    )
    points = np.array(
        [[width // 2, 0], [width // 4, height // 3], [3 * width // 4, height // 3]],
        dtype=np.int32,
    )
    cv2.fillConvexPoly(bgra, points, (25, 25, 25, 255), cv2.LINE_AA)
    return bgra[:, :, :3].astype(np.float32), bgra[:, :, 3].astype(np.float32) / 255.0


class TipOverlay:
    def __init__(
        self,
        image: np.ndarray,
        alpha: np.ndarray,
        *,
        tip_anchor_x: float,
        tip_anchor_y: float,
    ) -> None:
        self.image = image
        self.alpha = alpha
        self.anchor_x = tip_anchor_x
        self.anchor_y = tip_anchor_y

    def stamp(self, frame: np.ndarray, tip_x: int, tip_y: int) -> None:
        height, width = self.alpha.shape
        left = round(tip_x - width * self.anchor_x)
        top = round(tip_y - height * self.anchor_y)
        frame_height, frame_width = frame.shape[:2]
        x0, y0 = max(0, left), max(0, top)
        x1, y1 = min(frame_width, left + width), min(frame_height, top + height)
        if x0 >= x1 or y0 >= y1:
            return
        source_x0, source_y0 = x0 - left, y0 - top
        source_x1, source_y1 = source_x0 + (x1 - x0), source_y0 + (y1 - y0)
        alpha = self.alpha[source_y0:source_y1, source_x0:source_x1, None]
        source = self.image[source_y0:source_y1, source_x0:source_x1]
        target = frame[y0:y1, x0:x1].astype(np.float32)
        frame[y0:y1, x0:x1] = (source * alpha + target * (1.0 - alpha)).astype(np.uint8)


def _feathered_disk(radius: int) -> np.ndarray:
    coordinates = np.arange(-radius, radius + 1, dtype=np.float32)
    x, y = np.meshgrid(coordinates, coordinates)
    distance = np.sqrt(x * x + y * y)
    feather = max(1.0, radius * 0.2)
    return np.clip((radius - distance) / feather, 0.0, 1.0)


def _ease_in_out_sine(value: float | np.ndarray) -> float | np.ndarray:
    return -(np.cos(np.pi * value) - 1.0) / 2.0


def _build_wipe_wave(width: int) -> np.ndarray:
    x = np.linspace(0.0, 1.0, width, dtype=np.float32)
    return (
        np.sin(x * np.pi * 4.0) * 5.0
        + np.sin(x * np.pi * 11.0 + 0.7) * 2.3
        + np.sin(x * np.pi * 23.0 + 1.2) * 0.9
    ).astype(np.float32)


def _skeleton_neighbors(image: np.ndarray) -> tuple[np.ndarray, ...]:
    return (
        image[:-2, 1:-1],
        image[:-2, 2:],
        image[1:-1, 2:],
        image[2:, 2:],
        image[2:, 1:-1],
        image[2:, :-2],
        image[1:-1, :-2],
        image[:-2, :-2],
    )


def _thinning_pass(image: np.ndarray, second: bool) -> bool:
    neighbors = _skeleton_neighbors(image)
    neighbor_count = sum(neighbors)
    transitions = sum(
        (neighbors[index] == 0) & (neighbors[(index + 1) % 8] == 1)
        for index in range(8)
    )
    p2, _p3, p4, _p5, p6, _p7, p8, _p9 = neighbors
    center = image[1:-1, 1:-1]
    if second:
        triplet_a = p2 * p4 * p8
        triplet_b = p2 * p6 * p8
    else:
        triplet_a = p2 * p4 * p6
        triplet_b = p4 * p6 * p8
    remove = (
        (center == 1)
        & (neighbor_count >= 2)
        & (neighbor_count <= 6)
        & (transitions == 1)
        & (triplet_a == 0)
        & (triplet_b == 0)
    )
    if not remove.any():
        return False
    center[remove] = 0
    return True


def _zhang_suen_skeleton(mask: np.ndarray, max_iterations: int = 160) -> np.ndarray:
    image = mask.astype(np.uint8).copy()
    for _ in range(max_iterations):
        changed_a = _thinning_pass(image, False)
        changed_b = _thinning_pass(image, True)
        if not changed_a and not changed_b:
            break
    return image.astype(bool)


_PIXEL_NEIGHBORS = [
    (-1, -1),
    (0, -1),
    (1, -1),
    (-1, 0),
    (1, 0),
    (-1, 1),
    (0, 1),
    (1, 1),
]


def _pixel_neighbors(skeleton: np.ndarray, point: tuple[int, int]) -> list[tuple[int, int]]:
    x, y = point
    height, width = skeleton.shape
    return [
        (x + dx, y + dy)
        for dx, dy in _PIXEL_NEIGHBORS
        if 0 <= x + dx < width and 0 <= y + dy < height and skeleton[y + dy, x + dx]
    ]


def _edge_key(
    first: tuple[int, int], second: tuple[int, int]
) -> tuple[tuple[int, int], tuple[int, int]]:
    return (first, second) if first <= second else (second, first)


def _choose_next(
    previous: tuple[int, int],
    current: tuple[int, int],
    candidates: list[tuple[int, int]],
    visited_edges: set[tuple[tuple[int, int], tuple[int, int]]],
) -> tuple[int, int] | None:
    fresh = [candidate for candidate in candidates if _edge_key(current, candidate) not in visited_edges]
    if not fresh:
        return None
    incoming = (current[0] - previous[0], current[1] - previous[1])
    return min(
        fresh,
        key=lambda candidate: (
            -(
                incoming[0] * (candidate[0] - current[0])
                + incoming[1] * (candidate[1] - current[1])
            ),
            candidate,
        ),
    )


def trace_8connected(
    skeleton: np.ndarray, min_points: int = 8
) -> list[list[tuple[int, int]]]:
    rows, columns = np.nonzero(skeleton)
    points = [(int(x), int(y)) for x, y in zip(columns, rows, strict=True)]
    if not points:
        return []
    degrees = {point: len(_pixel_neighbors(skeleton, point)) for point in points}
    starts = [point for point in points if degrees[point] == 1]
    starts.extend(point for point in points if degrees[point] > 2)
    starts.extend(points)
    visited_edges: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    strokes: list[list[tuple[int, int]]] = []
    for start in starts:
        for neighbor in _pixel_neighbors(skeleton, start):
            edge = _edge_key(start, neighbor)
            if edge in visited_edges:
                continue
            path = [start]
            previous, current = start, neighbor
            visited_edges.add(edge)
            while True:
                path.append(current)
                following = _choose_next(
                    previous,
                    current,
                    _pixel_neighbors(skeleton, current),
                    visited_edges,
                )
                if following is None:
                    break
                visited_edges.add(_edge_key(current, following))
                previous, current = current, following
            if len(path) >= min_points:
                strokes.append(path)
    return strokes


def _stroke_cumulative_length(points: list[tuple[float, float]]) -> list[float]:
    cumulative = [0.0]
    for first, second in zip(points, points[1:], strict=False):
        cumulative.append(
            cumulative[-1] + math.hypot(second[0] - first[0], second[1] - first[1])
        )
    return cumulative


def _resample_stroke_points(
    points: list[tuple[float, float]], spacing: float
) -> list[tuple[float, float]]:
    if len(points) < 2 or spacing <= 0:
        return list(points)
    cumulative = _stroke_cumulative_length(points)
    total = cumulative[-1]
    if total <= spacing:
        return [points[0], points[-1]]
    distances = np.arange(0.0, total, spacing).tolist()
    if not math.isclose(distances[-1], total):
        distances.append(total)
    result: list[tuple[float, float]] = []
    segment = 0
    for distance in distances:
        while segment + 1 < len(cumulative) and cumulative[segment + 1] < distance:
            segment += 1
        if segment + 1 >= len(points):
            result.append(points[-1])
            continue
        span = cumulative[segment + 1] - cumulative[segment]
        ratio = 0.0 if span <= 1e-9 else (distance - cumulative[segment]) / span
        first, second = points[segment], points[segment + 1]
        result.append(
            (
                first[0] + (second[0] - first[0]) * ratio,
                first[1] + (second[1] - first[1]) * ratio,
            )
        )
    return result


def _chaikin_smooth(
    points: list[tuple[float, float]], iterations: int = 1
) -> list[tuple[float, float]]:
    smoothed = list(points)
    for _ in range(iterations):
        if len(smoothed) < 3:
            break
        result = [smoothed[0]]
        for first, second in zip(smoothed, smoothed[1:], strict=False):
            result.append(
                (first[0] * 0.75 + second[0] * 0.25, first[1] * 0.75 + second[1] * 0.25)
            )
            result.append(
                (first[0] * 0.25 + second[0] * 0.75, first[1] * 0.25 + second[1] * 0.75)
            )
        result.append(smoothed[-1])
        smoothed = result
    return smoothed


def _order_skeleton_strokes(
    strokes: list[list[tuple[float, float]]],
) -> list[list[tuple[float, float]]]:
    if not strokes:
        return []
    remaining = [list(stroke) for stroke in strokes]
    remaining.sort(key=lambda stroke: (stroke[0][1], stroke[0][0]))
    ordered = [remaining.pop(0)]
    while remaining:
        endpoint = ordered[-1][-1]
        best_index = 0
        best_reverse = False
        best_distance = math.inf
        for index, stroke in enumerate(remaining):
            for reverse, point in ((False, stroke[0]), (True, stroke[-1])):
                distance = (point[0] - endpoint[0]) ** 2 + (point[1] - endpoint[1]) ** 2
                if distance < best_distance:
                    best_index, best_reverse, best_distance = index, reverse, distance
        selected = remaining.pop(best_index)
        ordered.append(list(reversed(selected)) if best_reverse else selected)
    return ordered
