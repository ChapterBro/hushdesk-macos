"""Shared helpers for rendering MAR previews with a single orientation matrix."""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple, Union

import fitz  # PyMuPDF
import logging
import os

logger = logging.getLogger(__name__)
_DEBUG = os.getenv("HUSHDESK_RENDER_DEBUG", "").lower() in ("1", "true", "yes", "on")

try:  # pragma: no cover - optional dependency during CLI / tests
    from PySide6.QtGui import QImage, QPixmap  # type: ignore
except Exception:  # pragma: no cover - PySide6 not available (eg. headless tests)
    QImage = None  # type: ignore
    QPixmap = None  # type: ignore

RectTuple = Tuple[float, float, float, float]
PointTuple = Tuple[float, float]
RenderedPixmap = Union["QPixmap", fitz.Pixmap]


def make_render_matrix(
    page: fitz.Page,
    *,
    target_dpi: int = 110,
    force_landscape: bool = True,
) -> fitz.Matrix:
    """
    Build a deterministic render matrix that neutralizes PDF rotates before scaling.

    The resulting matrix lets us normalize every page once and optionally force a
    landscape preview regardless of the PDF's /Rotate metadata.
    """
    rotation = (page.rotation or 0) % 360
    neutralize = (360 - rotation) % 360
    scale = target_dpi / 72.0
    matrix = fitz.Matrix(scale, scale).prerotate(neutralize)
    rect_after = fitz.Rect(page.rect).transform(matrix)
    if force_landscape and rect_after.height > rect_after.width:
        matrix = matrix.prerotate(90)
        rect_after = fitz.Rect(page.rect).transform(matrix)
    if _DEBUG:
        try:
            logger.debug(
                "render_matrix page=%s rot=%s neutral=%s force_landscape=%s dpi=%s scale=%.3f out=%dx%d",
                getattr(page, "number", None),
                rotation,
                neutralize,
                force_landscape,
                target_dpi,
                scale,
                int(rect_after.width),
                int(rect_after.height),
            )
        except Exception:
            # Debug logging should never break rendering; swallow PyMuPDF errors here.
            pass
    return matrix


def render_page_surface(
    doc: fitz.Document,
    page_index: int,
    *,
    target_dpi: int = 110,
    force_landscape: bool = True,
    page: Optional[fitz.Page] = None,
) -> Tuple[fitz.Pixmap, fitz.Matrix]:
    """Render the requested page and return the PyMuPDF pixmap plus matrix."""
    page_obj = page if page is not None else doc.load_page(page_index)
    matrix = make_render_matrix(
        page_obj,
        target_dpi=target_dpi,
        force_landscape=force_landscape,
    )
    pix = page_obj.get_pixmap(matrix=matrix, alpha=False)
    if force_landscape and pix.height > pix.width:
        try:
            matrix = matrix.prerotate(90)
            pix = page_obj.get_pixmap(matrix=matrix, alpha=False)
        except Exception:
            if _DEBUG:
                logger.exception("Fail-safe prerotate render attempt failed for page %s", getattr(page_obj, "number", None))
    return pix, matrix


def render_page_pixmap(
    doc: fitz.Document,
    page_index: int,
    *,
    target_dpi: int = 110,
    force_landscape: bool = True,
) -> Tuple[RenderedPixmap, fitz.Matrix]:
    """
    Render a page for UI display.

    Returns (QPixmap, matrix) when PySide6 is available; otherwise the raw PyMuPDF
    pixmap is returned in place of the QPixmap so headless tests can still run.
    """
    pix, matrix = render_page_surface(
        doc,
        page_index,
        target_dpi=target_dpi,
        force_landscape=force_landscape,
    )
    if QImage is None or QPixmap is None:
        return pix, matrix
    return qpixmap_from_fitz(pix), matrix


def qpixmap_from_fitz(pix: fitz.Pixmap) -> "QPixmap":
    """Convert a PyMuPDF pixmap to a detached QPixmap."""
    if QImage is None or QPixmap is None:
        raise RuntimeError("PySide6 is required to convert pixmaps.")
    fmt = QImage.Format_RGB888 if pix.alpha == 0 else QImage.Format_RGBA8888
    image = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
    return QPixmap.fromImage(image)


def rect_points_to_pixels(
    rect: Optional[Sequence[float]],
    matrix: fitz.Matrix,
) -> Optional[RectTuple]:
    """Project an (x0, y0, x1, y1) rectangle into rendered pixel space."""
    if rect is None:
        return None
    if len(rect) != 4:
        return None
    x0, y0, x1, y1 = map(float, rect)
    width = x1 - x0
    height = y1 - y0
    if width <= 0.0 or height <= 0.0:
        return None
    projected = fitz.Rect(x0, y0, x1, y1).transform(matrix)
    return (
        float(projected.x0),
        float(projected.y0),
        float(projected.width),
        float(projected.height),
    )


def rect_pixels_to_points(
    rect: Optional[Sequence[float]],
    scale: float,
) -> Optional[RectTuple]:
    """
    Convert a previously scaled (x, y, width, height) rectangle back to page points.
    """
    if rect is None:
        return None
    if len(rect) != 4:
        return None
    x, y, width, height = map(float, rect)
    if width <= 0.0 or height <= 0.0:
        return None
    factor = 1.0 / scale if scale not in (0.0, -0.0) else 1.0
    return (
        x * factor,
        y * factor,
        (x + width) * factor,
        (y + height) * factor,
    )


def transform_point_from_pixels(
    point: Optional[Sequence[float]],
    scale: float,
    matrix: fitz.Matrix,
) -> Optional[PointTuple]:
    """Convert a pixel point back to page space and project it with the matrix."""
    if point is None or len(point) < 2:
        return None
    x, y = map(float, point[:2])
    factor = 1.0 / scale if scale not in (0.0, -0.0) else 1.0
    page_point = fitz.Point(x * factor, y * factor).transform(matrix)
    return (float(page_point.x), float(page_point.y))


def transform_point_from_page(
    point: Optional[Sequence[float]],
    matrix: fitz.Matrix,
) -> Optional[PointTuple]:
    """Project a page-space point using the provided matrix."""
    if point is None or len(point) < 2:
        return None
    page_point = fitz.Point(float(point[0]), float(point[1])).transform(matrix)
    return (float(page_point.x), float(page_point.y))


def project_rect_list(
    rects: Iterable[Sequence[float]],
    matrix: fitz.Matrix,
) -> List[RectTuple]:
    """Project an iterable of page rectangles to device pixels."""
    results: List[RectTuple] = []
    for rect in rects:
        projected = rect_points_to_pixels(rect, matrix)
        if projected is not None:
            results.append(projected)
    return results


__all__ = [
    "make_render_matrix",
    "render_page_surface",
    "render_page_pixmap",
    "qpixmap_from_fitz",
    "rect_points_to_pixels",
    "rect_pixels_to_points",
    "transform_point_from_pixels",
    "transform_point_from_page",
    "project_rect_list",
]
