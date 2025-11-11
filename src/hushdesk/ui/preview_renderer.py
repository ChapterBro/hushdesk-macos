"""Shared helpers for deterministic MAR page rendering."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple, Union

import hashlib
import logging
import os

import fitz  # type: ignore

from .renderer_cache import CacheKey, PixCache

logger = logging.getLogger(__name__)
_DEBUG = os.getenv("HUSHDESK_RENDER_DEBUG", "").lower() in {"1", "true", "yes", "on"}

try:  # pragma: no cover - optional dependency during headless tests
    from PySide6.QtGui import QImage, QPixmap  # type: ignore
except Exception:  # pragma: no cover
    QImage = None  # type: ignore
    QPixmap = None  # type: ignore

RectTuple = Tuple[float, float, float, float]
PointTuple = Tuple[float, float]
RenderedPixmap = Union["QPixmap", bytes]

_CACHE = PixCache(
    max_bytes=int(os.getenv("HUSHDESK_RENDER_CACHE_BYTES", 180 * 1024 * 1024))
)


def _normalize_region_key(region: Optional[Sequence[float]]) -> Tuple[int, int, int, int]:
    if region and len(region) >= 4:
        values = [int(round(float(value))) for value in region[:4]]
        return (values[0], values[1], values[2], values[3])
    return (0, 0, 0, 0)


def _doc_sha_from_doc(
    doc: Optional[fitz.Document],
    pdf_path: str | Path | None = None,
) -> str:
    hints: List[str] = []
    if pdf_path:
        hints.append(str(Path(pdf_path).expanduser()))
    for attr in ("name", "filePath", "filename"):
        value = getattr(doc, attr, None) if doc is not None else None
        if value:
            hints.append(str(value))
    for hint in hints:
        try:
            resolved = str(Path(hint).expanduser().resolve())
        except Exception:
            resolved = str(hint)
        if resolved:
            return hashlib.sha256(resolved.encode("utf-8")).hexdigest()
    token = f"doc:{id(doc)}"
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _cache_key(
    doc_sha: str,
    page_index: int,
    target_dpi: int,
    region_key: Tuple[int, int, int, int],
) -> CacheKey:
    return CacheKey(
        doc_sha=doc_sha,
        page_index=int(page_index),
        dpi=int(target_dpi),
        region=region_key,
    )


@dataclass(frozen=True)
class RenderMeta:
    """Metadata describing a rendered MAR preview."""

    page_index: Optional[int]
    dpi: int
    scale: float
    original_rotation: int
    neutralized_rotation: int
    width: int
    height: int
    force_landscape: bool
    fail_safe_used: bool
    clip: Optional[RectTuple]


def make_render_matrix(page: fitz.Page, *, target_dpi: int = 144) -> fitz.Matrix:
    """Create a matrix that neutralizes /Rotate before scaling to ``target_dpi``."""

    rotation = (page.rotation or 0) % 360
    neutralize = (360 - rotation) % 360
    scale = target_dpi / 72.0
    matrix = fitz.Matrix(scale, scale).prerotate(neutralize)
    if _DEBUG:
        rect_after = fitz.Rect(page.rect).transform(matrix)
        logger.debug(
            "RENDER_MATRIX page=%s rot=%s neutral=%s dpi=%s out=%dx%d",
            getattr(page, "number", None),
            rotation,
            neutralize,
            target_dpi,
            int(rect_after.width),
            int(rect_after.height),
        )
    return matrix


def render_page_surface(
    page: fitz.Page,
    *,
    page_index: Optional[int] = None,
    target_dpi: int = 144,
    force_landscape: bool = True,
    region: Optional[Sequence[float]] = None,
) -> Tuple[fitz.Pixmap, fitz.Matrix, RenderMeta]:
    """Render ``page`` to a PyMuPDF pixmap plus matrix + metadata."""

    clip_rect = _clip_rect(region)
    matrix = make_render_matrix(page, target_dpi=target_dpi)
    pix = page.get_pixmap(matrix=matrix, alpha=False, clip=clip_rect)
    fail_safe = False
    if force_landscape and pix.height > pix.width:
        matrix = matrix.prerotate(90)
        pix = page.get_pixmap(matrix=matrix, alpha=False, clip=clip_rect)
        fail_safe = True
    meta = RenderMeta(
        page_index=page_index,
        dpi=target_dpi,
        scale=target_dpi / 72.0,
        original_rotation=int(page.rotation or 0),
        neutralized_rotation=int((page.rotation or 0) % 360),
        width=int(pix.width),
        height=int(pix.height),
        force_landscape=force_landscape,
        fail_safe_used=fail_safe,
        clip=_rect_tuple(clip_rect),
    )
    if _DEBUG:
        logger.debug(
            "RENDER_PIX page=%s size=%dx%d force_landscape=%s fail_safe=%s clip=%s",
            meta.page_index if meta.page_index is not None else getattr(page, "number", None),
            meta.width,
            meta.height,
            force_landscape,
            fail_safe,
            meta.clip,
        )
    return pix, matrix, meta


def render_page_pixmap(
    page: fitz.Page,
    *,
    page_index: Optional[int] = None,
    target_dpi: int = 144,
    force_landscape: bool = True,
    region: Optional[Sequence[float]] = None,
) -> Tuple[RenderedPixmap, fitz.Matrix, RenderMeta]:
    """Render ``page`` and return a Qt pixmap when available, else PNG bytes."""

    pix, matrix, meta = render_page_surface(
        page,
        page_index=page_index,
        target_dpi=target_dpi,
        force_landscape=force_landscape,
        region=region,
    )
    return _convert_pixmap(pix), matrix, meta


def render_document_page(
    doc: fitz.Document,
    page_index: int,
    *,
    target_dpi: int = 144,
    force_landscape: bool = True,
    region: Optional[Sequence[float]] = None,
    cache_hint: str | Path | None = None,
) -> Tuple[RenderedPixmap, fitz.Matrix, RenderMeta]:
    """Render ``page_index`` inside ``doc`` using the shared renderer."""

    region_key = _normalize_region_key(region)
    doc_sha = _doc_sha_from_doc(doc, cache_hint)
    key = _cache_key(doc_sha, page_index, target_dpi, region_key)
    cached = _CACHE.get(key)
    if cached:
        return cached
    page = doc.load_page(page_index)
    result = render_page_pixmap(
        page,
        page_index=page_index,
        target_dpi=target_dpi,
        force_landscape=force_landscape,
        region=region,
    )
    meta = result[2]
    _CACHE.put(key, result, meta.width, meta.height)
    return result


def render_pdf_page(
    pdf_path: str | Path,
    page_index: int,
    *,
    target_dpi: int = 144,
    force_landscape: bool = True,
    region: Optional[Sequence[float]] = None,
) -> Tuple[RenderedPixmap, fitz.Matrix, RenderMeta]:
    """Render ``page_index`` from ``pdf_path`` and close the document automatically."""

    source = Path(pdf_path).expanduser()
    try:
        resolved_source = source.resolve()
    except FileNotFoundError:
        resolved_source = source
    region_key = _normalize_region_key(region)
    doc_sha = _doc_sha_from_doc(None, resolved_source)
    key = _cache_key(doc_sha, page_index, target_dpi, region_key)
    cached = _CACHE.get(key)
    if cached:
        return cached
    with fitz.open(str(resolved_source)) as doc:  # type: ignore[attr-defined]
        return render_document_page(
            doc,
            page_index,
            target_dpi=target_dpi,
            force_landscape=force_landscape,
            region=region,
            cache_hint=resolved_source,
        )


def qpixmap_from_fitz(pix: fitz.Pixmap) -> "QPixmap":
    """Convert a PyMuPDF pixmap to a detached :class:`QPixmap`."""

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

    if rect is None or len(rect) != 4:
        return None
    x0, y0, x1, y1 = map(float, rect)
    projected = fitz.Rect(x0, y0, x1, y1).transform(matrix)
    width = float(projected.width)
    height = float(projected.height)
    if width <= 0.0 or height <= 0.0:
        return None
    return (
        float(projected.x0),
        float(projected.y0),
        width,
        height,
    )


def rect_pixels_to_points(
    rect: Optional[Sequence[float]],
    scale: float,
) -> Optional[RectTuple]:
    """Convert a scaled (x, y, width, height) rectangle back to points."""

    if rect is None or len(rect) != 4:
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
    """Convert a pixel point back to page space and project it with ``matrix``."""

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
    """Project a page-space point using ``matrix``."""

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
        if projected:
            results.append(projected)
    return results


def _convert_pixmap(pix: fitz.Pixmap) -> RenderedPixmap:
    if QImage is None or QPixmap is None:
        return pix.tobytes("png")
    return qpixmap_from_fitz(pix)


def _clip_rect(region: Optional[Sequence[float]]) -> Optional[fitz.Rect]:
    if region is None or len(region) < 4:
        return None
    x0, y0, x1, y1 = map(float, region[:4])
    if x1 == x0 or y1 == y0:
        return None
    return fitz.Rect(x0, y0, x1, y1)


def _rect_tuple(rect: Optional[fitz.Rect]) -> Optional[RectTuple]:
    if rect is None:
        return None
    width = float(rect.width)
    height = float(rect.height)
    if width <= 0.0 or height <= 0.0:
        return None
    return (float(rect.x0), float(rect.y0), width, height)


__all__ = [
    "RectTuple",
    "PointTuple",
    "RenderedPixmap",
    "RenderMeta",
    "make_render_matrix",
    "render_page_surface",
    "render_page_pixmap",
    "render_document_page",
    "render_pdf_page",
    "rect_points_to_pixels",
    "rect_pixels_to_points",
    "transform_point_from_pixels",
    "transform_point_from_page",
    "project_rect_list",
]
