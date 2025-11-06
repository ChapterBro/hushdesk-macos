"""Canonical PyMuPDF page extraction helpers."""

from __future__ import annotations

import sys
from dataclasses import dataclass as _dataclass
from pathlib import Path
from typing import Iterator, List, Optional, Sequence, Tuple, Union

try:  # pragma: no cover - optional dependency during docs builds
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore

Point = Tuple[float, float]
BBox = Tuple[float, float, float, float]

_LINE_FLAT_TOLERANCE = 0.75


if sys.version_info >= (3, 10):
    def _dataclass_slotted(*args, **kwargs):
        return _dataclass(*args, **kwargs)
else:  # pragma: no cover - Python <3.10 compatibility for debug scripts
    def _dataclass_slotted(*args, **kwargs):
        kwargs.pop("slots", None)
        return _dataclass(*args, **kwargs)


@_dataclass_slotted(slots=True)
class CanonWord:
    """A single word extracted from the PDF with canonical coordinates."""

    text: str
    bbox: BBox
    center: Point


@_dataclass_slotted(slots=True)
class CanonLine:
    """A vector line (horizontal/vertical) extracted from drawing commands."""

    orientation: str  # "h" or "v"
    p0: Point
    p1: Point


@_dataclass_slotted(slots=True)
class CanonPage:
    """A page with MuPDF canonical coordinates and shared derotation matrix."""

    page_index: int
    width: float
    height: float
    words: List[CanonWord]
    vlines: List[CanonLine]
    hlines: List[CanonLine]
    matrix: "fitz.Matrix"
    pixmap: "fitz.Pixmap"
    raw_page: Optional["fitz.Page"] = None


DocumentLike = Union[str, Path, "fitz.Document"]


def canonical_matrix(page: "fitz.Page", scale: float = 2.0) -> "fitz.Matrix":
    """Return the MuPDF matrix that derotates + scales into canonical coordinates."""

    if fitz is None:  # pragma: no cover - handled by callers
        raise RuntimeError("PyMuPDF (fitz) is required for canonical matrices")

    rotation_scale = fitz.Matrix(scale, scale).prerotate(-page.rotation)
    rotated_rect = fitz.Rect(page.rect) * rotation_scale
    rotation_scale.e -= rotated_rect.x0
    rotation_scale.f -= rotated_rect.y0
    return rotation_scale


def iter_canon_pages(source: DocumentLike, scale: float = 2.0) -> Iterator[CanonPage]:
    """Yield ``CanonPage`` objects with rotation-normalized coordinates."""

    if fitz is None:  # pragma: no cover - handled by callers
        raise RuntimeError("PyMuPDF (fitz) is required for iter_canon_pages")

    close_doc = False
    if isinstance(source, (str, Path)):
        doc = fitz.open(str(source))
        close_doc = True
    elif isinstance(source, fitz.Document):
        doc = source
    else:  # pragma: no cover - defensive
        raise TypeError(f"Unsupported document source type: {type(source)!r}")

    try:
        for page_index in range(doc.page_count):
            page = doc.load_page(page_index)
            yield build_canon_page(page_index, page, scale=scale)
    finally:
        if close_doc:
            doc.close()


def build_canon_page(page_index: int, page: "fitz.Page", *, scale: float = 2.0) -> CanonPage:
    """Return a ``CanonPage`` applying the MuPDF canonical derotation matrix."""

    matrix = canonical_matrix(page, scale=scale)
    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
    width = float(pixmap.width)
    height = float(pixmap.height)
    words = _extract_words(page, matrix, width, height)
    vlines, hlines = _extract_lines(page, matrix, width, height)
    return CanonPage(
        page_index=page_index,
        width=width,
        height=height,
        words=words,
        vlines=vlines,
        hlines=hlines,
        matrix=matrix,
        pixmap=pixmap,
        raw_page=page,
    )


def _extract_words(
    page: "fitz.Page",
    matrix: "fitz.Matrix",
    page_width: float,
    page_height: float,
) -> List[CanonWord]:
    try:
        raw_words = page.get_text("words", clip=page.rect)
    except RuntimeError:
        return []

    words: List[CanonWord] = []
    for entry in raw_words:
        if len(entry) < 5:
            continue
        x0, y0, x1, y1 = map(float, entry[0:4])
        text = str(entry[4])
        if not text.strip():
            continue
        corners = [
            fitz.Point(x0, y0),
            fitz.Point(x1, y0),
            fitz.Point(x0, y1),
            fitz.Point(x1, y1),
        ]
        transformed = [pt * matrix for pt in corners]
        xs = [pt.x for pt in transformed]
        ys = [pt.y for pt in transformed]
        nx0 = float(max(0.0, min(xs)))
        nx1 = float(min(page_width, max(xs)))
        ny0 = float(max(0.0, min(ys)))
        ny1 = float(min(page_height, max(ys)))
        cx = (nx0 + nx1) / 2.0
        cy = (ny0 + ny1) / 2.0
        words.append(CanonWord(text=text, bbox=(nx0, ny0, nx1, ny1), center=(cx, cy)))
    return words


def _extract_lines(
    page: "fitz.Page",
    matrix: "fitz.Matrix",
    page_width: float,
    page_height: float,
) -> Tuple[List[CanonLine], List[CanonLine]]:
    drawings: Sequence[dict]
    try:
        drawings = page.get_drawings()
    except RuntimeError:
        drawings = []

    vlines: List[CanonLine] = []
    hlines: List[CanonLine] = []

    for drawing in drawings:
        for item in drawing.get("items", ()):
            if not item:
                continue
            if item[0] != "l":
                continue
            p0_raw, p1_raw = item[1:3]
            p0 = _transform_point(p0_raw, matrix, page_width, page_height)
            p1 = _transform_point(p1_raw, matrix, page_width, page_height)
            if _is_horizontal(p0, p1):
                hlines.append(CanonLine("h", p0, p1))
            elif _is_vertical(p0, p1):
                vlines.append(CanonLine("v", p0, p1))

    return vlines, hlines


def _transform_point(
    point: Point,
    matrix: "fitz.Matrix",
    page_width: float,
    page_height: float,
) -> Point:
    px = fitz.Point(point) * matrix
    x = float(min(page_width, max(0.0, px.x)))
    y = float(min(page_height, max(0.0, px.y)))
    return x, y


def _is_horizontal(p0: Point, p1: Point) -> bool:
    return abs(p0[1] - p1[1]) <= _LINE_FLAT_TOLERANCE and abs(p0[0] - p1[0]) >= 1.0


def _is_vertical(p0: Point, p1: Point) -> bool:
    return abs(p0[0] - p1[0]) <= _LINE_FLAT_TOLERANCE and abs(p0[1] - p1[1]) >= 1.0


__all__ = [
    "CanonPage",
    "CanonWord",
    "CanonLine",
    "build_canon_page",
    "canonical_matrix",
    "iter_canon_pages",
]
