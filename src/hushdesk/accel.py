"""Optional Rust accelerators with safe Python fallbacks."""

from __future__ import annotations

import math
import os
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

USE_RUST = bool(os.getenv("HUSHDESK_USE_RUST"))

try:  # pragma: no cover - optional native extension
    from hushdesk_accel import (  # type: ignore[import]
        select_bands as select_bands_rs,
        stitch_bp as stitch_bp_rs,
        y_cluster as y_cluster_rs,
    )

    ACCEL_AVAILABLE = True
except Exception:  # pragma: no cover - extension not present
    ACCEL_AVAILABLE = False

_CENTER_MERGE_EPSILON = 2.0
_MIN_BAND_WIDTH = 5.0
_BP_PREFIX_RE = re.compile(r"(?<!\d)(\d{2,3})\s*/\s*$")
_DIGITS_ONLY_RE = re.compile(r"^\d{2,3}$")


def _coerce_floats(values: Iterable[float]) -> List[float]:
    result: List[float] = []
    for value in values:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(numeric):
            continue
        result.append(numeric)
    return result


def _y_cluster_py(points: Sequence[float], bin_px: int) -> List[float]:
    if not points:
        return []

    bin_size = float(bin_px) if bin_px else 1.0
    clusters: Dict[int, List[float]] = {}
    for value in _coerce_floats(points):
        key = int(round(value / bin_size))
        clusters.setdefault(key, []).append(value)

    centers = []
    for items in clusters.values():
        if not items:
            continue
        centers.append(sum(items) / len(items))

    centers.sort()
    return centers


def _stitch_bp_py(lines: Sequence[str]) -> Optional[str]:
    if len(lines) < 2:
        return None

    normalized = [str(line).strip() for line in lines]
    for index, text in enumerate(normalized):
        if not text:
            continue
        match = _BP_PREFIX_RE.match(text)
        if not match:
            continue
        prefix = match.group(1)
        for neighbor in normalized[index + 1 :]:
            if _DIGITS_ONLY_RE.fullmatch(neighbor):
                return f"{int(prefix)}/{int(neighbor)}"
    return None


def _collapse_center_group(group: List[Tuple[int, float]]) -> List[Tuple[int, float]]:
    if not group:
        return []
    if len(group) == 1:
        return group
    day_values = {day for day, _ in group}
    if len(day_values) == 1:
        day = group[0][0]
        merged_center = sum(center for _, center in group) / len(group)
        return [(day, merged_center)]
    return group


def _select_bands_py(
    centers: Sequence[Tuple[int, float]],
    page_width: float,
) -> Dict[int, Tuple[float, float]]:
    if not centers:
        return {}

    by_day: Dict[int, List[float]] = {}
    for day, center in centers:
        try:
            day_int = int(day)
        except (TypeError, ValueError):
            continue
        try:
            center_value = float(center)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(center_value):
            continue
        by_day.setdefault(day_int, []).append(center_value)

    averaged = [(day, sum(values) / len(values)) for day, values in by_day.items() if values]
    averaged.sort(key=lambda item: item[1])

    merged: List[Tuple[int, float]] = []
    if averaged:
        group: List[Tuple[int, float]] = [averaged[0]]
        for day, center in averaged[1:]:
            if abs(center - group[-1][1]) <= _CENTER_MERGE_EPSILON:
                group.append((day, center))
            else:
                merged.extend(_collapse_center_group(group))
                group = [(day, center)]
        merged.extend(_collapse_center_group(group))

    count = len(merged)
    if count == 0:
        return {}

    bands: Dict[int, Tuple[float, float]] = {}
    for index, (day, center_x) in enumerate(merged):
        if count == 1:
            x0 = 0.0
            x1 = page_width
        elif index == 0:
            next_center = merged[index + 1][1]
            delta = (next_center - center_x) / 2.0
            x0 = center_x - delta
            x1 = center_x + delta
        elif index == count - 1:
            prev_center = merged[index - 1][1]
            delta = (center_x - prev_center) / 2.0
            x0 = center_x - delta
            x1 = center_x + delta
        else:
            prev_center = merged[index - 1][1]
            next_center = merged[index + 1][1]
            x0 = center_x - (center_x - prev_center) / 2.0
            x1 = center_x + (next_center - center_x) / 2.0

        x0 = max(0.0, x0)
        x1 = min(page_width, x1)
        if x1 < x0:
            x0, x1 = x1, x0
        if x1 <= x0:
            continue
        if (x1 - x0) < _MIN_BAND_WIDTH:
            continue
        bands[day] = (x0, x1)

    return bands


def y_cluster(points: Sequence[float], bin_px: int) -> List[float]:
    values = list(points)
    if USE_RUST and ACCEL_AVAILABLE:
        try:
            return list(y_cluster_rs(values, bin_px))
        except Exception:
            pass
    return _y_cluster_py(values, bin_px)


def stitch_bp(lines: Sequence[str]) -> Optional[str]:
    values = [str(line) for line in lines]
    if USE_RUST and ACCEL_AVAILABLE:
        try:
            return stitch_bp_rs(values)
        except Exception:
            pass
    return _stitch_bp_py(values)


def select_bands(
    centers: Sequence[Tuple[int, float]],
    page_width: float,
) -> Dict[int, Tuple[float, float]]:
    values = list(centers)
    if USE_RUST and ACCEL_AVAILABLE:
        try:
            mapping = select_bands_rs(values, page_width)
            return dict(mapping)  # type: ignore[arg-type]
        except Exception:
            pass
    return _select_bands_py(values, page_width)


__all__ = [
    "ACCEL_AVAILABLE",
    "USE_RUST",
    "select_bands",
    "stitch_bp",
    "y_cluster",
]
