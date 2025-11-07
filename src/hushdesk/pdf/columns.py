"""Column selection helpers for MAR audit grids."""

from __future__ import annotations

from datetime import date
from dataclasses import dataclass
from typing import Callable, List, Optional

try:  # pragma: no cover - optional dependency when tests run without PyMuPDF
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore

from .mar_header import band_for_date
from .mupdf_canon import build_canon_page


@dataclass(slots=True)
class ColumnBand:
    page_index: int
    x0: float
    x1: float
    page_width: float
    page_height: float
    frac0: float
    frac1: float
    canonical_x0: Optional[float] = None
    canonical_x1: Optional[float] = None
    page_x0: Optional[float] = None
    page_x1: Optional[float] = None


def select_audit_columns(
    doc: "fitz.Document",
    audit_date: date,
    *,
    on_page_without_header: Optional[Callable[[int], None]] = None,
) -> List[ColumnBand]:
    """Return per-page column bands that match ``audit_date``."""

    results: List[ColumnBand] = []

    for page_index in range(doc.page_count):
        page = doc.load_page(page_index)
        canon_page = build_canon_page(page_index, page)
        band = band_for_date(canon_page, audit_date)
        if not band:
            if on_page_without_header is not None:
                on_page_without_header(page_index)
            continue

        canon_x0, canon_x1 = band
        rect = page.rect
        page_width = float(rect.width)
        page_height = float(rect.height)
        derotated_rect = rect * page.derotation_matrix
        canon_width = float(derotated_rect.width)
        canon_height = float(derotated_rect.height)

        if canon_x1 <= canon_x0 or (canon_x1 - canon_x0) < 5.0:
            continue
        if canon_width <= 0:
            frac0 = frac1 = 0.0
        else:
            frac0 = canon_x0 / canon_width
            frac1 = canon_x1 / canon_width

        rotation_matrix = page.rotation_matrix
        y0_canon = float(derotated_rect.y0)
        y1_canon = float(derotated_rect.y1)
        corners = [
            fitz.Point(canon_x0, y0_canon) * rotation_matrix,
            fitz.Point(canon_x0, y1_canon) * rotation_matrix,
            fitz.Point(canon_x1, y0_canon) * rotation_matrix,
            fitz.Point(canon_x1, y1_canon) * rotation_matrix,
        ]
        xs = [corner.x for corner in corners]
        page_x0 = min(xs)
        page_x1 = max(xs)

        results.append(
            ColumnBand(
                page_index=page_index,
                x0=canon_x0,
                x1=canon_x1,
                page_width=canon_width,
                page_height=canon_height,
                frac0=frac0,
                frac1=frac1,
                canonical_x0=canon_x0,
                canonical_x1=canon_x1,
                page_x0=page_x0,
                page_x1=page_x1,
            )
        )

    return results
