from __future__ import annotations

import os

from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QSizePolicy,
)


class PreviewView(QGraphicsView):
    """
    A drop-in view that keeps previews centered and free of clipping:
      - sceneRect tracks the pixmap bounds
      - resize events debounce into a deterministic refit
      - fit/zoom modes consistently update scrollbars + alignment
      - optional debug traces via HUSHDESK_PREVIEW_DEBUG
    """

    _FIT_ALIASES = {
        "fit-page": "page",
        "fit-width": "width",
        "fit-height": "height",
        "fit-region": "region",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setFrameShape(QFrame.NoFrame)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

        self._refit_timer = QTimer(self)
        self._refit_timer.setSingleShot(True)
        self._refit_timer.setInterval(0)
        self._refit_timer.timeout.connect(self._apply_fit)

        self._pix: QGraphicsPixmapItem | None = None
        self._fit_mode: str = "page"  # {"actual","page","width","height","region","custom"}
        self._custom_zoom: float = 1.0
        self._region_rect: QRectF | None = None

    # --- public API -----------------------------------------------------
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
        """Set a ROI used when ``fit_mode == "region"``."""

        if rect is None or rect.isNull():
            self._region_rect = None
        else:
            self._region_rect = QRectF(rect)
        if self._fit_mode == "region":
            self._apply_fit()

    def has_region_rect(self) -> bool:
        return self._region_rect is not None and not self._region_rect.isNull()

    def set_fit_mode(self, mode: str) -> str:
        """Apply one of the supported fit modes and return the resolved mode."""

        normalized = (mode or "").strip().lower()
        normalized = self._FIT_ALIASES.get(normalized, normalized)
        valid = {"actual", "page", "width", "height", "region"}
        self._fit_mode = normalized if normalized in valid else "custom"
        if self._fit_mode == "region" and not self.has_region_rect():
            self._fit_mode = "page"
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

    # --- events ---------------------------------------------------------
    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._refit_timer.start()

    # --- helpers --------------------------------------------------------
    def _scrollbars_for_mode(self) -> None:
        fit_modes = {"page", "width", "height", "region"}
        if self._fit_mode in fit_modes:
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        else:
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    def _apply_fit(self) -> None:
        self._scrollbars_for_mode()

        pix = self._pix
        if pix is None:
            return

        rect = pix.sceneBoundingRect()
        if rect.isNull():
            return

        target = rect
        if self._fit_mode == "region" and self._region_rect and not self._region_rect.isNull():
            target = self._region_rect

        self.resetTransform()

        if self._fit_mode == "actual":
            self.centerOn(target.center())
            self._debug_trace(rect)
            return

        if self._fit_mode == "custom":
            self.scale(self._custom_zoom, self._custom_zoom)
            self.centerOn(target.center())
            self._debug_trace(rect, custom=True)
            return

        if self._fit_mode in {"page", "region"}:
            self.fitInView(target, Qt.KeepAspectRatio)
            self.centerOn(target.center())
            self._debug_trace(rect)
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
        else:
            scale = min(view_w / width, view_h / height)

        self.scale(scale, scale)
        self.centerOn(target.center())
        self._debug_trace(rect, scale=scale)

    def _debug_trace(self, rect: QRectF, *, scale: float | None = None, custom: bool = False) -> None:
        if not os.getenv("HUSHDESK_PREVIEW_DEBUG"):
            return
        try:
            viewport = self.viewport()
            if viewport is None:
                return
            vp = viewport.rect()
            scale_desc = f" scale={scale:.3f}" if scale is not None else ""
            if custom:
                scale_desc = f" scale={self._custom_zoom:.3f}"
            print(
                "[PreviewView]"
                f" mode={self._fit_mode}"
                f"{scale_desc}"
                f" viewport={vp.width()}x{vp.height()}"
                f" scene={int(rect.width())}x{int(rect.height())}"
            )
        except Exception:
            pass
