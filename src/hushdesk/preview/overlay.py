"""Helpers to render MAR page previews with overlay highlights."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

try:  # pragma: no cover - optional during headless tests
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap


RectTuple = Tuple[float, float, float, float]


def render_band_preview(
    pdf_path: str,
    page_index: int,
    overlays: Dict[str, object],
    out_png_path: Path,
) -> Path:
    """Render the requested page with audit overlays and persist as PNG."""
    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) is required to render previews.")

    overlays = dict(overlays or {})
    page_pixels = overlays.get("page_pixels")
    scale = 1.0
    if isinstance(page_pixels, dict):
        try:
            value = float(page_pixels.get("scale", 1.0))
            if value > 0:
                scale = value
        except (TypeError, ValueError):
            scale = 1.0

    with fitz.open(pdf_path) as doc:  # type: ignore[attr-defined]
        if page_index < 0 or page_index >= len(doc):
            raise IndexError(f"Page index {page_index} out of range for preview.")
        page = doc.load_page(page_index)
        if scale <= 0.0:
            width_pt = float(page.rect.width or 0.0)
            target_width = 1600.0
            scale = max(1.0, target_width / width_pt) if width_pt > 0 else 1.0
        matrix = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=matrix)
        pix.save(str(out_png_path))

    pixmap = QPixmap(str(out_png_path))
    if pixmap.isNull():
        return out_png_path

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    _draw_rect(
        painter,
        _rect_from_overlay(overlays.get("audit_band")),
        QColor("#3A7BFF"),
        fill_alpha=60,
        pen_width=3,
    )

    slot_rects = overlays.get("slot_bboxes")
    if isinstance(slot_rects, dict):
        am_rect = _rect_from_overlay(slot_rects.get("AM"))
        pm_rect = _rect_from_overlay(slot_rects.get("PM"))
        _draw_rect(painter, am_rect, QColor("#22C55E"), fill_alpha=50, pen_width=2)
        _draw_rect(painter, pm_rect, QColor("#F97316"), fill_alpha=50, pen_width=2)

    _draw_rect(
        painter,
        _rect_from_overlay(overlays.get("vital_bbox")),
        QColor("#00FF7F"),
        fill_alpha=80,
        pen_width=3,
    )

    mark_rects = overlays.get("mark_bboxes")
    if isinstance(mark_rects, Iterable):
        for rect in mark_rects:
            _draw_rect(
                painter,
                _rect_from_overlay(rect),
                QColor("#FF2E88"),
                fill_alpha=70,
                pen_width=2,
            )

    labels = overlays.get("labels")
    if isinstance(labels, Iterable):
        painter.setPen(QPen(QColor("#1F2937")))
        for label in labels:
            if not isinstance(label, dict):
                continue
            text = str(label.get("text") or "").strip()
            if not text:
                continue
            try:
                x = float(label.get("x", 0.0))
                y = float(label.get("y", 0.0))
            except (TypeError, ValueError):
                continue
            painter.drawText(QRectF(x, y, 320.0, 40.0), text)

    painter.end()
    pixmap.save(str(out_png_path), "PNG")
    return out_png_path


def _rect_from_overlay(value: object) -> Optional[RectTuple]:
    if isinstance(value, (list, tuple)) and len(value) == 4:
        x, y, w, h = value
        try:
            width = float(w)
            height = float(h)
        except (TypeError, ValueError):
            return None
        if width <= 0.0 or height <= 0.0:
            return None
        try:
            return (
                float(x),
                float(y),
                width,
                height,
            )
        except (TypeError, ValueError):
            return None
    return None


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
