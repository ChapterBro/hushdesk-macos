from __future__ import annotations
import os

from PySide6.QtCore import Qt, QRectF, QTimer
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
        self._refit_timer.timeout.connect(self._apply_fit)
        self._refit_timer.setInterval(0)
        self._refit_timer.setSingleShot(True)
        self._refit_timer = QTimer(self)
        self.setAlignment(Qt.AlignCenter)
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
        # debounce refit to avoid jitter on Retina/fullscreen
        if hasattr(self, '_refit_timer'):
            self._refit_timer.start()
        self.scale(scale, scale)

    def _scrollbars_for_mode(self):
        if getattr(self, "_fit_mode", "fit-page") in ("fit-page", "fit-width", "fit-height"):
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        else:
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
