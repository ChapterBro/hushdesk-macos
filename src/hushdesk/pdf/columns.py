"""Column selection helpers for MAR audit grids."""

from __future__ import annotations

from datetime import date
from dataclasses import dataclass
from typing import List

try:  # pragma: no cover - optional dependency when tests run without PyMuPDF
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore

from hushdesk.pdf.layout import bands_from_day_centers, find_day_header_centers


@dataclass(slots=True)
class ColumnBand:
    page_index: int
    x0: float
    x1: float
    page_width: float
    page_height: float
    frac0: float
    frac1: float


def select_audit_columns(doc: "fitz.Document", audit_date: date) -> List[ColumnBand]:
    """Return per-page column bands that match ``audit_date``."""

    target_day = audit_date.day
    results: List[ColumnBand] = []

    for page_index in range(doc.page_count):
        page = doc.load_page(page_index)
        centers = find_day_header_centers(page)
        if not centers:
            continue

        rect = page.rect
        page_width = float(rect.width)
        page_height = float(rect.height)
        day_bands = bands_from_day_centers(centers, page_width, page_height)
        band = day_bands.get(target_day)
        if not band:
            continue

        x0, x1, width, height = band
        if width <= 0:
            frac0 = frac1 = 0.0
        else:
            frac0 = x0 / width
            frac1 = x1 / width

        results.append(
            ColumnBand(
                page_index=page_index,
                x0=x0,
                x1=x1,
                page_width=width,
                page_height=height,
                frac0=frac0,
                frac1=frac1,
            )
        )

    return results
