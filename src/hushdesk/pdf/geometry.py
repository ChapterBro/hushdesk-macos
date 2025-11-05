"""Geometry helpers for PDF coordinate normalization."""

from __future__ import annotations

from typing import Tuple

Rect = Tuple[float, float, float, float]


def normalize_rect(rect: Rect) -> Rect:
    """Return ``rect`` with coordinates sorted so that x1 >= x0 and y1 >= y0."""

    x0, y0, x1, y1 = rect
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    return float(x0), float(y0), float(x1), float(y1)
