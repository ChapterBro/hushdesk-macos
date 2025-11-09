"""Helpers to render MAR page previews with overlay highlights."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

try:  # pragma: no cover - optional during headless tests
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from hushdesk.ui.preview_renderer import (
    qpixmap_from_fitz,
    rect_pixels_to_points,
    rect_points_to_pixels,
    render_page_surface,
    transform_point_from_pixels,
)


RectTuple = Tuple[float, float, float, float]


def render_band_preview(
    pdf_path: str,
    page_index: int,
    overlays: Dict[str, object],
    out_png_path: Path,
) -> Tuple[Path, Dict[str, object]]:
    """
    Render the requested page with audit overlays and persist as PNG.

    Returns a tuple of (output_path, projected_overlays) so the caller can reuse
    the same orientation-aware overlay coordinates.
    """
    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) is required to render previews.")

    overlays = dict(overlays or {})
    page_pixels = overlays.get("page_pixels") if isinstance(overlays.get("page_pixels"), dict) else {}
    overlay_scale = _safe_scale(page_pixels)

    with fitz.open(pdf_path) as doc:  # type: ignore[attr-defined]
        if page_index < 0 or page_index >= len(doc):
            raise IndexError(f"Page index {page_index} out of range for preview.")
        page = doc.load_page(page_index)
        pix, matrix = render_page_surface(
            doc,
            page_index,
            target_dpi=_dpi_from_scale(overlay_scale, page.rect.width),
            page=page,
        )

    pixmap = qpixmap_from_fitz(pix)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    projected_overlays = _project_preview_overlays(overlays, overlay_scale, matrix)

    _draw_rect(
        painter,
        projected_overlays.get("audit_band"),
        QColor("#3A7BFF"),
        fill_alpha=60,
        pen_width=3,
    )

    slot_rects = projected_overlays.get("slot_bboxes", {})
    if isinstance(slot_rects, dict):
        am_rect = slot_rects.get("AM")
        pm_rect = slot_rects.get("PM")
        _draw_rect(painter, am_rect, QColor("#22C55E"), fill_alpha=50, pen_width=2)
        _draw_rect(painter, pm_rect, QColor("#F97316"), fill_alpha=50, pen_width=2)

    _draw_rect(
        painter,
        projected_overlays.get("vital_bbox"),
        QColor("#00FF7F"),
        fill_alpha=80,
        pen_width=3,
    )

    mark_rects = projected_overlays.get("mark_bboxes", [])
    if isinstance(mark_rects, Iterable):
        for rect in mark_rects:
            _draw_rect(painter, rect, QColor("#FF2E88"), fill_alpha=70, pen_width=2)

    labels = projected_overlays.get("labels") or projected_overlays.get("overlay_labels")
    if isinstance(labels, Iterable):
        painter.setPen(QPen(QColor("#1F2937")))
        for label in labels:
            if not isinstance(label, dict):
                continue
            text = str(label.get("text") or "").strip()
            if not text:
                continue
            try:
                x = float(label["x"])
                y = float(label["y"])
            except (KeyError, TypeError, ValueError):
                continue
            painter.drawText(QRectF(x, y, 320.0, 40.0), text)

    painter.end()
    pixmap.save(str(out_png_path), "PNG")
    return out_png_path, projected_overlays


def _safe_scale(page_pixels: Dict[str, object]) -> float:
    try:
        value = float(page_pixels.get("scale", 1.0))
    except (AttributeError, TypeError, ValueError):
        return 1.0
    return value if value > 0 else 1.0


def _dpi_from_scale(scale: float, page_width_pt: float) -> int:
    if scale <= 0.0:
        width_pt = float(page_width_pt or 0.0)
        target_width = 1600.0
        computed = max(1.0, target_width / width_pt) if width_pt > 0 else 1.0
    else:
        computed = scale
    return max(72, int(round(computed * 72.0)))


def _project_preview_overlays(
    overlays: Dict[str, object],
    overlay_scale: float,
    matrix: "fitz.Matrix",
) -> Dict[str, object]:
    projected: Dict[str, object] = {}
    projected["audit_band"] = _project_rect_value(overlays.get("audit_band"), overlay_scale, matrix)

    slot_rects = overlays.get("slot_bboxes") if isinstance(overlays.get("slot_bboxes"), dict) else {}
    slot_pixels: Dict[str, RectTuple] = {}
    for key, rect in slot_rects.items():
        converted = _project_rect_value(rect, overlay_scale, matrix)
        if converted:
            slot_pixels[str(key)] = converted
    if slot_pixels:
        projected["slot_bboxes"] = slot_pixels

    projected["vital_bbox"] = _project_rect_value(overlays.get("vital_bbox"), overlay_scale, matrix)

    mark_rects = overlays.get("mark_bboxes") if isinstance(overlays.get("mark_bboxes"), (list, tuple)) else []
    mark_pixels = []
    for rect in mark_rects:
        converted = _project_rect_value(rect, overlay_scale, matrix)
        if converted:
            mark_pixels.append(converted)
    if mark_pixels:
        projected["mark_bboxes"] = mark_pixels

    labels = overlays.get("overlay_labels") or overlays.get("labels")
    projected_labels = []
    if isinstance(labels, list):
        for label in labels:
            if not isinstance(label, dict):
                continue
            pos = transform_point_from_pixels(
                (label.get("x"), label.get("y")),
                overlay_scale,
                matrix,
            )
            if not pos:
                continue
            updated = dict(label)
            updated["x"], updated["y"] = pos
            projected_labels.append(updated)
    if projected_labels:
        projected["labels"] = projected_labels
        projected["overlay_labels"] = projected_labels

    return projected


def _project_rect_value(
    rect: object,
    overlay_scale: float,
    matrix: "fitz.Matrix",
) -> Optional[RectTuple]:
    page_rect = rect_pixels_to_points(rect, overlay_scale)
    if page_rect is None:
        return None
    return rect_points_to_pixels(page_rect, matrix)


def _draw_rect(
    painter: QPainter,
    rect: Optional[RectTuple],
    color: QColor,
    *,
    fill_alpha: int,
    pen_width: int,
) -> None:
    if rect is None:
        return
    x, y, width, height = rect
    if width <= 0.0 or height <= 0.0:
        return
    fill_color = QColor(color)
    fill_color.setAlpha(max(0, min(255, fill_alpha)))
    painter.fillRect(QRectF(x, y, width, height), fill_color)
    pen = QPen(color)
    pen.setWidth(max(1, pen_width))
    painter.setPen(pen)
    painter.drawRect(QRectF(x, y, width, height))
