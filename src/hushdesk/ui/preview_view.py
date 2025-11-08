from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QSizePolicy


class PreviewView(QGraphicsView):
    """
    A drop-in view that never clips:
      - always sets sceneRect to pixmap bounds
      - resets transform and fits on every resize
      - supports simple mode switching without stale transforms
    """

    def __init__(self, parent=None):
        super().__init__(QGraphicsScene(), parent)
        self.setFrameShape(self.NoFrame)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self._pix: QGraphicsPixmapItem | None = None
        self._fit_mode: str = "page"  # {"actual","page","width","height","region","custom"}
        self._custom_zoom: float = 1.0
        self._region_rect: QRectF | None = None

    # --- public API ---
    def clear(self) -> None:
        """Remove all scene items and reset scaling."""

        self.scene().clear()
        self._pix = None
        self._region_rect = None
        self.resetTransform()

    def pixmap_item(self) -> QGraphicsPixmapItem | None:
        return self._pix

    def set_pixmap(self, qpix: QPixmap | None) -> QGraphicsPixmapItem | None:
        """Replace the current pixmap with ``qpix``."""

        self.scene().clear()
        self._pix = None
        if qpix is None or qpix.isNull():
            return None
        item = QGraphicsPixmapItem(qpix)
        self.scene().addItem(item)
        self.scene().setSceneRect(item.boundingRect())
        self._pix = item
        self.resetTransform()
        self._apply_fit()
        return item

    def set_region_rect(self, rect: QRectF | None) -> None:
        """Set an optional region to prioritize when using the region fit mode."""

        if rect is None or rect.isNull():
            self._region_rect = None
        else:
            self._region_rect = QRectF(rect)
        if self._fit_mode == "region":
            self._apply_fit()

    def set_fit_mode(self, mode: str) -> str:
        """Apply one of the supported fit modes and return the resolved mode."""

        valid = {"actual", "page", "width", "height", "region"}
        self._fit_mode = mode if mode in valid else "custom"
        self._apply_fit()
        return self._fit_mode

    def set_custom_zoom(self, scale: float) -> float:
        """Set an explicit zoom factor (1.0 == 100%)."""

        self._custom_zoom = max(0.1, min(8.0, float(scale)))
        self._fit_mode = "custom"
        self._apply_fit()
        return self._custom_zoom

    def zoom_factor(self) -> float:
        return self._custom_zoom

    # --- events ---
    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._apply_fit()

    # --- helpers ---
    def _apply_fit(self) -> None:
        if not self._pix:
            return
        rect = self._pix.sceneBoundingRect()
        if rect.isNull():
            return

        target = rect
        if self._fit_mode == "region" and self._region_rect is not None and not self._region_rect.isNull():
            target = self._region_rect

        self.resetTransform()
        if self._fit_mode == "actual":
            return
        if self._fit_mode == "custom":
            self.scale(self._custom_zoom, self._custom_zoom)
            return
        if self._fit_mode in {"page", "region"}:
            # Keep entire target visible without rotation
            self.fitInView(target, Qt.KeepAspectRatio)
            return

        viewport = self.viewport()
        if viewport is None:
            return
        width = target.width()
        height = target.height()
        if width <= 0.0 or height <= 0.0:
            return

        view_w = max(1, viewport.width())
        view_h = max(1, viewport.height())
        if self._fit_mode == "width":
            scale = view_w / width
        elif self._fit_mode == "height":
            scale = view_h / height
        else:  # fallback to full fit
            scale = min(view_w / width, view_h / height)
        self.scale(scale, scale)
