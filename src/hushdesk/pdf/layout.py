"""Helpers for MAR calendar layout detection."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import DefaultDict, Dict, Iterable, List, Tuple

try:  # pragma: no cover - optional dependency when tests run without PyMuPDF
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore

RowBucket = List[Tuple[int, float]]

_ROW_MERGE_TOLERANCE = 6.0


def _iter_header_day_words(page: "fitz.Page") -> Iterable[Tuple[int, float, float]]:
    """Yield header-candidate ``(day, x_center, y_center)`` tuples."""

    try:
        words = page.get_text("words")
    except RuntimeError:
        return []

    matrix = page.derotation_matrix
    derotated_rect = page.rect * matrix
    page_height = float(derotated_rect.height or 0.0)
    header_limit = derotated_rect.y0 + page_height * 0.35 if page_height else float("inf")

    candidates: List[Tuple[int, float, float]] = []
    for entry in words:
        if len(entry) < 5:
            continue
        text = str(entry[4] if len(entry) > 4 else entry[0]).strip()
        if not text:
            continue
        normalized = text.strip(" .")
        if not normalized.isdigit():
            continue
        day = int(normalized)
        if day < 1 or day > 31:
            continue
        x0, y0, x1, y1 = map(float, entry[0:4])
        p0 = fitz.Point(x0, y0) * matrix
        p1 = fitz.Point(x1, y1) * matrix
        x_center = (p0.x + p1.x) / 2.0
        y_center = (p0.y + p1.y) / 2.0
        if y_center > header_limit:
            continue
        candidates.append((day, x_center, y_center))

    return candidates


def find_day_header_centers(page: "fitz.Page") -> List[Tuple[int, float]]:
    """Return a sorted list of ``(day, x_center_pt)`` for the header row."""

    candidates = list(_iter_header_day_words(page))
    if not candidates:
        return []

    row_map: Dict[float, RowBucket] = {}
    row_keys: List[float] = []

    for day, x_center, y_center in candidates:
        row_key = None
        for key in row_keys:
            if abs(y_center - key) <= _ROW_MERGE_TOLERANCE:
                row_key = key
                break
        if row_key is None:
            row_key = y_center
            row_keys.append(row_key)
            row_map[row_key] = []
        row_map[row_key].append((day, x_center))

    best_key = None
    best_score: Tuple[int, float] = (-1, float("inf"))
    for key in row_keys:
        values = row_map[key]
        unique_days = {day for day, _ in values}
        score = (len(unique_days), key)
        if best_key is None or (score[0] > best_score[0]) or (
            score[0] == best_score[0] and score[1] < best_score[1]
        ):
            best_key = key
            best_score = score

    if best_key is None:
        return []

    grouped: DefaultDict[int, List[float]] = defaultdict(list)
    for day, x_center in row_map[best_key]:
        grouped[day].append(x_center)

    return [(day, mean(xs)) for day, xs in sorted(grouped.items())]


def bands_from_day_centers(
    centers: List[Tuple[int, float]], page_width: float, page_height: float
) -> Dict[int, Tuple[float, float, float, float]]:
    """Return per-day column bands based on header center coordinates."""

    if not centers:
        return {}

    sorted_centers = sorted(centers, key=lambda item: item[1])
    x_positions = [x for _, x in sorted_centers]
    if len(x_positions) == 1:
        width = max(min(page_width, 24.0), page_width * 0.03)
        center = x_positions[0]
        x0 = max(0.0, center - width / 2.0)
        x1 = min(page_width, center + width / 2.0)
        day = int(sorted_centers[0][0])
        return {day: (x0, x1, page_width, page_height)}

    bands: Dict[int, Tuple[float, float, float, float]] = {}
    for index, (day, center) in enumerate(sorted_centers):
        prev_center = x_positions[index - 1] if index > 0 else None
        next_center = x_positions[index + 1] if index + 1 < len(x_positions) else None

        if prev_center is None:
            gap_left = next_center - center if next_center is not None else page_width * 0.04
        else:
            gap_left = center - prev_center

        if next_center is None:
            gap_right = center - prev_center if prev_center is not None else page_width * 0.04
        else:
            gap_right = next_center - center

        width_left = max(4.0, abs(gap_left) / 2.0)
        width_right = max(4.0, abs(gap_right) / 2.0)

        x0 = center - width_left
        x1 = center + width_right
        x0 = max(0.0, x0)
        x1 = min(page_width, x1)
        bands[int(day)] = (x0, x1, page_width, page_height)

    return bands
