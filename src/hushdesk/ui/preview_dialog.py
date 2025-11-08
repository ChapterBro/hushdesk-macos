"""Modal preview dialog that overlays audit highlights on MAR pages."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Dict, Iterable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
)
from hushdesk.ui.preview_view import PreviewView


class _PreviewGraphicsView(PreviewView):
    """Graphics view with ctrl/cmd + wheel zoom support."""

    def wheelEvent(self, event):  # noqa: N802
        modifiers = event.modifiers()
        if modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
            angle = event.angleDelta().y()
            factor = 1.2 if angle > 0 else 1 / 1.2
            self.set_custom_zoom(self.zoom_factor() * factor)
            event.accept()
            return
        super().wheelEvent(event)


class PreviewDialog(QDialog):
    """Preview dialog with overlay rectangles and optional snapshot save."""

    def __init__(
        self,
        image_path: Path,
        overlays: Dict[str, object],
        parent: Optional[QDialog] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Decision Preview")
        self.resize(900, 720)
        self._image_path = Path(image_path)
        self._overlays = dict(overlays or {})

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        pixmap = QPixmap(str(self._image_path))
        self._view = _PreviewGraphicsView(self)
        self._view.setRenderHint(QGraphicsView.RenderHint.Antialiasing, True)
        self._view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self._view.set_pixmap(pixmap)
        layout.addWidget(self._view, stretch=1)

        self._add_overlay_items(self._view.scene())
        self._view.set_fit_mode("page")

        buttons = QDialogButtonBox(Qt.Orientation.Horizontal)
        snapshot_button = QPushButton("Save Snapshot")
        snapshot_button.clicked.connect(self._save_snapshot)
        buttons.addButton(snapshot_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)

        layout.addWidget(buttons)

    # ------------------------------------------------------------------ helpers

    def _add_overlay_items(self, scene: QGraphicsScene) -> None:
        audit_rect = _rect_from_overlay(self._overlays.get("audit_band"))
        if audit_rect:
            scene.addItem(_build_rect_item(audit_rect, QColor("#3A7BFF"), 60, 3))

        slot_rects = self._overlays.get("slot_bboxes")
        if isinstance(slot_rects, dict):
            am_rect = _rect_from_overlay(slot_rects.get("AM"))
            pm_rect = _rect_from_overlay(slot_rects.get("PM"))
            if am_rect:
                scene.addItem(_build_rect_item(am_rect, QColor("#22C55E"), 50, 2))
            if pm_rect:
                scene.addItem(_build_rect_item(pm_rect, QColor("#F97316"), 50, 2))

        vital_rect = _rect_from_overlay(self._overlays.get("vital_bbox"))
        if vital_rect:
            scene.addItem(_build_rect_item(vital_rect, QColor("#00FF7F"), 70, 3))

        mark_rects = self._overlays.get("mark_bboxes")
        if isinstance(mark_rects, Iterable):
            for rect in mark_rects:
                converted = _rect_from_overlay(rect)
                if converted:
                    scene.addItem(_build_rect_item(converted, QColor("#FF2E88"), 60, 2))

        labels = self._overlays.get("overlay_labels")
        if isinstance(labels, Iterable):
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
                text_item = QGraphicsSimpleTextItem(text)
                text_item.setBrush(QColor("#111827"))
                text_item.setPos(x, y)
                background = _build_rect_item((x - 4, y - 4, text_item.boundingRect().width() + 8, text_item.boundingRect().height() + 8), QColor("#F9FAFB"), 220, 1)
                background.setZValue(5)
                text_item.setZValue(6)
                scene.addItem(background)
                scene.addItem(text_item)

    def _save_snapshot(self) -> None:
        default_path = Path.home() / "Desktop" / f"HushDeskPreview-{_dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Save Preview Snapshot",
            str(default_path),
            "PNG Image (*.png)",
        )
        if not target:
            return
        grab = self._view.grab()
        grab.save(target, "PNG")


def _rect_from_overlay(value: object) -> Optional[tuple[float, float, float, float]]:
    if isinstance(value, (list, tuple)) and len(value) == 4:
        try:
            x, y, w, h = map(float, value)
        except (TypeError, ValueError):
            return None
        if w <= 0.0 or h <= 0.0:
            return None
        return (x, y, w, h)
    return None


def _build_rect_item(
    rect: tuple[float, float, float, float],
    color: QColor,
    alpha: int,
    pen_width: int,
) -> QGraphicsRectItem:
    x, y, w, h = rect
    brush = QColor(color)
    brush.setAlpha(max(0, min(255, alpha)))
    pen = QPen(color)
    pen.setWidth(max(1, pen_width))
    item = QGraphicsRectItem(x, y, w, h)
    item.setBrush(brush)
    item.setPen(pen)
    item.setZValue(4)
    return item
