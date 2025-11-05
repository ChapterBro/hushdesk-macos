"""Helpers for MAR calendar layout detection."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import DefaultDict, Dict, Iterable, List, Tuple

try:  # pragma: no cover - optional dependency when tests run without PyMuPDF
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore

from hushdesk.accel import select_bands

RowBucket = List[Tuple[int, float]]

_ROW_MERGE_TOLERANCE = 3.0


def _iter_numeric_spans(page: "fitz.Page") -> Iterable[Tuple[int, float, float]]:
    """Yield candidate day numbers and their centers from ``page`` spans."""

    try:
        text = page.get_text("dict")
    except RuntimeError:
        return []

    candidates: List[Tuple[int, float, float]] = []
    for block in text.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                raw_text = str(span.get("text", "")).strip()
                if not raw_text or not raw_text.isdigit():
                    continue
                day = int(raw_text)
                if day < 1 or day > 31:
                    continue

                bbox = span.get("bbox")
                if not bbox or len(bbox) != 4:
                    continue
                x0, y0, x1, y1 = map(float, bbox)
                x_center = (x0 + x1) / 2.0
                y_center = (y0 + y1) / 2.0
                candidates.append((day, x_center, y_center))

    return candidates


def find_day_header_centers(page: "fitz.Page") -> List[Tuple[int, float]]:
    """Return a sorted list of ``(day, x_center_pt)`` for the header row."""

    candidates = list(_iter_numeric_spans(page))
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

    band_pairs = select_bands(centers, page_width)
    bands: Dict[int, Tuple[float, float, float, float]] = {}
    for day, (x0, x1) in band_pairs.items():
        bands[int(day)] = (x0, x1, page_width, page_height)
    return bands
