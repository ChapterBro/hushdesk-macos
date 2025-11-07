"""Evidence drawer showing rule context and PDF preview overlays."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QEvent, QObject, Qt, QUrl, QRectF
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

try:  # pragma: no cover - optional dependency
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore

from hushdesk.pdf.mupdf_canon import canonical_matrix


class EvidencePanel(QWidget):
    """Right-side drawer with decision details and PDF previews."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        allow_open_pdf: bool = True,
    ) -> None:
        super().__init__(parent)
        self._allow_open_pdf = allow_open_pdf
        self._record: Optional[dict] = None
        self._pdf_path: Optional[Path] = None
        self._preview_cache: Dict[Tuple[str, int], QPixmap] = {}
        self._current_preview_pixmap: Optional[QPixmap] = None
        self._preview_scale_pct = 100
        self._fit_mode = "custom"
        self._pixmap_item: Optional[QGraphicsPixmapItem] = None
        self._current_scale = 1.0
        self._active_roi: Optional[QRectF] = None
        self._preview_meta: Optional[dict] = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setChildrenCollapsible(False)
        layout.addWidget(self.splitter, stretch=1)

        meta_panel = QWidget()
        meta_layout = QVBoxLayout(meta_panel)
        meta_layout.setContentsMargins(0, 0, 0, 0)
        meta_layout.setSpacing(8)

        title = QLabel("Evidence")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        meta_layout.addWidget(title)

        self.summary_label = QLabel("Select a decision to view details.")
        self.summary_label.setWordWrap(True)
        meta_layout.addWidget(self.summary_label)

        self.details_label = QLabel()
        self.details_label.setWordWrap(True)
        self.details_label.setStyleSheet("color: #374151;")
        meta_layout.addWidget(self.details_label)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(8)

        self.open_button = QPushButton("Open PDF to page")
        self.open_button.clicked.connect(self._handle_open_pdf)
        self.open_button.setEnabled(False)
        if not self._allow_open_pdf:
            self.open_button.setVisible(False)
        button_row.addWidget(self.open_button)

        self.preview_button = QPushButton("Preview")
        self.preview_button.clicked.connect(self._handle_preview)
        self.preview_button.setEnabled(False)
        button_row.addWidget(self.preview_button)

        button_row.addStretch(1)
        self.zoom_badge = QLabel("—")
        self.zoom_badge.setObjectName("PreviewZoomBadge")
        self.zoom_badge.setStyleSheet("color: #6b7280; font-size: 11px; font-weight: 500;")
        button_row.addWidget(self.zoom_badge)

        meta_layout.addLayout(button_row)

        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(6)

        self.preview_status = QLabel("Preview not generated.")
        self.preview_status.setStyleSheet("color: #6b7280; font-size: 12px;")
        preview_layout.addWidget(self.preview_status)

        self.preview_scene = QGraphicsScene(self)
        self.previewScroll = QGraphicsView(self.preview_scene)
        self.previewScroll.setObjectName("PreviewView")
        self.previewScroll.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.previewScroll.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.previewScroll.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.previewScroll.viewport().installEventFilter(self)
        self.previewScroll.setBackgroundBrush(QColor("#f9fafb"))
        self.previewScroll.setStyleSheet("border: 1px solid #e5e7eb;")
        self.previewScroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.previewScroll.setMinimumHeight(520)
        preview_layout.addWidget(self.previewScroll, stretch=1)

        self.splitter.addWidget(meta_panel)
        self.splitter.addWidget(preview_panel)

    def clear(self, message: Optional[str] = None) -> None:
        self._record = None
        self._pdf_path = None
        self._current_preview_pixmap = None
        self._pixmap_item = None
        self._active_roi = None
        self._preview_meta = None
        self._current_scale = 1.0
        if hasattr(self, "preview_scene"):
            self.preview_scene.clear()
        if hasattr(self, "previewScroll"):
            self.previewScroll.resetTransform()
        self.summary_label.setText(message or "Select a decision to view details.")
        self.details_label.clear()
        self.preview_status.setText("Preview not generated.")
        self.open_button.setEnabled(False)
        self.preview_button.setEnabled(False)
        if hasattr(self, "zoom_badge"):
            self.zoom_badge.setText("—")

    def set_record(self, record: Optional[dict], pdf_path: Optional[Path]) -> None:
        self._record = dict(record) if isinstance(record, dict) else None
        self._pdf_path = Path(pdf_path) if isinstance(pdf_path, Path) else (Path(pdf_path) if isinstance(pdf_path, str) else None)
        if not self._record:
            self.clear()
            return

        summary = self._format_summary(self._record)
        self.summary_label.setText(summary)
        details = self._format_details(self._record)
        self.details_label.setText(details)

        has_pdf = self._pdf_path is not None and self._pdf_path.exists()
        page_index = self._extract_page_index(self._record)
        if self._allow_open_pdf:
            self.open_button.setEnabled(has_pdf and page_index is not None)
        else:
            self.open_button.setEnabled(False)
        can_preview = has_pdf and fitz is not None and page_index is not None
        self.preview_button.setEnabled(can_preview)
        self._apply_preview_metadata(self._record)
        if not can_preview:
            if fitz is None:
                self.preview_status.setText("Preview requires PyMuPDF.")
            elif not has_pdf:
                self.preview_status.setText("Source PDF not available.")
            else:
                self.preview_status.setText("Record missing page information.")
            self._current_preview_pixmap = None
            self._pixmap_item = None
            self.preview_scene.clear()
            self._update_zoom_badge()
            return
        self.preview_status.setText("Loading preview...")
        if not self._load_preview_pixmap(auto=True):
            self.preview_status.setText("Unable to render preview.")

    def has_region_roi(self) -> bool:
        return self._active_roi is not None

    def recommended_fit(self) -> Optional[str]:
        if not isinstance(self._preview_meta, dict):
            return None
        value = self._preview_meta.get("recommended_fit")
        return str(value) if isinstance(value, str) and value else None

    def _apply_preview_metadata(self, record: Optional[dict]) -> None:
        preview_meta = record.get("preview") if isinstance(record, dict) else None
        self._preview_meta = preview_meta if isinstance(preview_meta, dict) else None
        self._active_roi = self._roi_from_preview(self._preview_meta)

    @staticmethod
    def _roi_from_preview(preview_meta: Optional[dict]) -> Optional[QRectF]:
        if not isinstance(preview_meta, dict):
            return None
        roi = preview_meta.get("roi")
        if not isinstance(roi, (list, tuple)) or len(roi) < 4:
            return None
        try:
            x, y, width, height = (float(roi[0]), float(roi[1]), float(roi[2]), float(roi[3]))
        except (TypeError, ValueError):
            return None
        if width <= 0.0 or height <= 0.0:
            return None
        return QRectF(x, y, width, height)

    def _load_preview_pixmap(self, *, auto: bool = False, force: bool = False) -> bool:
        if not self._record or not self._pdf_path or fitz is None:
            return False
        cache_key = (str(self._pdf_path), int(self._record.get("id", -1)))
        pixmap = None if force else self._preview_cache.get(cache_key)
        if pixmap is None:
            pixmap = self._render_preview(self._record, self._pdf_path)
            if pixmap is None:
                return False
            self._preview_cache[cache_key] = pixmap
        self._current_preview_pixmap = pixmap
        if self._pixmap_item is None:
            self._pixmap_item = self.preview_scene.addPixmap(pixmap)
        else:
            self._pixmap_item.setPixmap(pixmap)
        self.preview_scene.setSceneRect(QRectF(pixmap.rect()))
        page_index = self._extract_page_index(self._record) or 0
        self.preview_status.setText(f"Preview: page {page_index + 1}.")
        self._apply_view_transform(recenter=auto or self._fit_mode != "custom")
        return True

    def _apply_view_transform(self, *, recenter: bool = False) -> None:
        pixmap = self._current_preview_pixmap
        if pixmap is None or self._pixmap_item is None:
            self.preview_scene.update()
            self.previewScroll.resetTransform()
            self._current_scale = 1.0
            self._update_zoom_badge()
            return
        viewport = self.previewScroll.viewport()
        viewport_width = max(1, viewport.width())
        viewport_height = max(1, viewport.height())
        base_width = max(1, pixmap.width())
        base_height = max(1, pixmap.height())
        mode = self._fit_mode
        if mode == "region" and not self._active_roi:
            mode = "width"
            self._fit_mode = "width"
        if mode == "width":
            scale = viewport_width / base_width
        elif mode == "height":
            scale = viewport_height / base_height
        elif mode == "page":
            scale = min(viewport_width / base_width, viewport_height / base_height)
        elif mode == "actual":
            scale = 1.0
        elif mode == "region" and self._active_roi:
            roi = self._active_roi
            scale = min(
                viewport_width / max(1.0, roi.width()),
                viewport_height / max(1.0, roi.height()),
            )
        else:
            scale = max(0.25, min(4.0, self._preview_scale_pct / 100.0))
        if scale <= 0:
            scale = 1.0
        self.previewScroll.setTransform(QTransform.fromScale(scale, scale))
        self._current_scale = scale
        drag_mode = (
            QGraphicsView.DragMode.ScrollHandDrag if scale > 1.01 else QGraphicsView.DragMode.NoDrag
        )
        self.previewScroll.setDragMode(drag_mode)
        if self._fit_mode == "region" and self._active_roi is not None:
            self.previewScroll.centerOn(self._active_roi.center())
        elif recenter:
            self.previewScroll.centerOn(self._pixmap_item.boundingRect().center())
        self._update_zoom_badge()

    def _update_zoom_badge(self) -> None:
        if not hasattr(self, "zoom_badge"):
            return
        if self._current_preview_pixmap is None:
            self.zoom_badge.setText("—")
            return
        pct = int(round(self._current_scale * 100))
        label = self._mode_label()
        self.zoom_badge.setText(f"{pct}%  |  {label}")

    def _mode_label(self) -> str:
        labels = {
            "width": "Fit Width",
            "height": "Fit Height",
            "page": "Fit Page",
            "region": "Region",
            "actual": "Actual",
            "custom": "Custom",
        }
        return labels.get(self._fit_mode, "Custom")

    def _handle_open_pdf(self) -> None:
        if not self._allow_open_pdf or not self._record or not self._pdf_path:
            return
        page_index = self._extract_page_index(self._record)
        if page_index is None:
            return
        page_number = page_index + 1
        url = QUrl.fromLocalFile(str(self._pdf_path))
        if not self._pdf_path.exists():
            QDesktopServices.openUrl(url)
            return
        try:
            self._launch_preview_script(self._pdf_path, page_number)
            self.preview_status.setText(f"Opened PDF to page {page_number}.")
        except Exception:
            QDesktopServices.openUrl(url)
            self.preview_status.setText(f"PDF opened; navigate to page {page_number}.")

    def _handle_preview(self) -> None:
        if not self._record or not self._pdf_path or fitz is None:
            return
        if not self._load_preview_pixmap(force=True):
            self.preview_status.setText("Unable to render preview.")

    @staticmethod
    def _format_summary(record: dict) -> str:
        kind = record.get("kind") or "-"
        room = record.get("room_bed") or "Unknown"
        dose = record.get("slot_label") or record.get("dose") or "-"
        notes = record.get("notes")
        line = f"{kind} — {room} ({dose})"
        return f"{line}\n{notes}" if notes else line

    @staticmethod
    def _format_details(record: dict) -> str:
        extras = record.get("extras", {}) if isinstance(record, dict) else {}
        rule = record.get("rule_text") or ""
        vital = record.get("vital_text") or ""
        mark = extras.get("mark_display") or record.get("mark_display") or "—"
        mark_kind = extras.get("mark_type")
        trigger = "True" if extras.get("triggered") else "False"
        source = EvidencePanel._describe_source(extras.get("source_type"), extras.get("source_flags"))
        page_number = extras.get("page_number")
        slot_label = record.get("slot_label") or record.get("dose") or "-"
        lines = []
        if rule:
            lines.append(f"Rule: {rule}")
        if vital:
            lines.append(f"Vital: {vital}")
        if mark_kind:
            lines.append(f"Due mark: {mark} ({mark_kind})")
        else:
            lines.append(f"Due mark: {mark}")
        lines.append(f"Trigger: {trigger}")
        lines.append(f"Source: {source}")
        if page_number:
            lines.append(f"Page: {page_number} · Slot: {slot_label}")
        return "\n".join(lines)

    def set_zoom_percent(self, pct: int) -> None:
        self._fit_mode = "custom"
        self._preview_scale_pct = max(25, min(400, int(pct)))
        self._apply_view_transform()

    def set_fit_mode(self, mode: str) -> str:
        normalized = (mode or "").lower()
        if normalized not in {"width", "height", "page", "region", "actual"}:
            normalized = "custom"
        if normalized == "region" and not self.has_region_roi():
            normalized = "width"
        self._fit_mode = normalized
        if normalized == "actual":
            self._preview_scale_pct = 100
        self._apply_view_transform(recenter=True)
        return self._fit_mode

    def current_zoom_percent(self) -> int:
        return int(round(self._current_scale * 100))

    def current_fit_mode(self) -> str:
        return self._fit_mode

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if (
            hasattr(self, "previewScroll")
            and obj is self.previewScroll.viewport()
            and event.type() == QEvent.Type.Resize
            and self._current_preview_pixmap is not None
        ):
            self._apply_view_transform()
        return super().eventFilter(obj, event)

    @staticmethod
    def _describe_source(source_type: Optional[str], flags: Optional[dict]) -> str:
        base = source_type or "label"
        extras: List[str] = []
        if isinstance(flags, dict):
            if flags.get("bp_label_missing") or flags.get("hr_label_missing"):
                extras.append("label-missing")
            if flags.get("given_detected"):
                extras.append("given-detected")
            if flags.get("explicit_mark"):
                extras.append("explicit-mark")
        if extras:
            return f"{base} ({', '.join(extras)})"
        return base

    @staticmethod
    def _extract_page_index(record: dict) -> Optional[int]:
        extras = record.get("extras") if isinstance(record, dict) else None
        value = extras.get("page_index") if isinstance(extras, dict) else None
        if isinstance(value, int):
            return value
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _launch_preview_script(pdf_path: Path, page_number: int) -> None:
        escaped_pdf = str(pdf_path).replace('"', '\\"')
        script_lines = [
            f'set pdfPath to POSIX file "{escaped_pdf}"',
            f'set pageNumber to {page_number}',
            "tell application \"Preview\"",
            "activate",
            "open pdfPath",
            "delay 0.3",
            "try",
            "set theDoc to front document",
            "go to page pageNumber of theDoc",
            "end try",
            "end tell",
        ]
        args: List[str] = ["osascript"]
        for line in script_lines:
            args.extend(["-e", line])
        subprocess.run(args, check=False)

    def _render_preview(self, record: dict, pdf_path: Path) -> Optional[QPixmap]:
        if fitz is None:
            return None
        page_index = self._extract_page_index(record)
        if page_index is None:
            return None
        extras = record.get("extras", {}) if isinstance(record, dict) else {}
        try:
            with fitz.open(pdf_path) as doc:  # type: ignore[attr-defined]
                if page_index < 0 or page_index >= len(doc):
                    return None
                page = doc.load_page(page_index)
                matrix = canonical_matrix(page, scale=2.0)
                pix = page.get_pixmap(matrix=matrix)
        except Exception:  # pragma: no cover - defensive
            return None

        pixmap = QPixmap()
        pixmap.loadFromData(pix.tobytes("png"))
        if pixmap.isNull():
            return None

        page_width = float(extras.get("page_width") or pix.width)
        page_height = float(extras.get("page_height") or pix.height)
        scale_x = pixmap.width() / page_width if page_width else 1.0
        scale_y = pixmap.height() / page_height if page_height else 1.0

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        band_rect = extras.get("band_rect")
        slot_rect = extras.get("slot_rect")
        due_rect = extras.get("due_rect")
        token_boxes = extras.get("token_boxes") if isinstance(extras.get("token_boxes"), dict) else {}

        self._draw_rect(painter, band_rect, scale_x, scale_y, QColor(37, 99, 235), 2, 30)
        self._draw_rect(painter, slot_rect, scale_x, scale_y, QColor(16, 185, 129), 3, 50)
        self._draw_rect(painter, due_rect, scale_x, scale_y, QColor(249, 115, 22), 3, 0)

        for rect in token_boxes.get("bp", []) if isinstance(token_boxes, dict) else []:
            self._draw_rect(painter, rect, scale_x, scale_y, QColor(139, 92, 246), 2, 60)
        for rect in token_boxes.get("hr", []) if isinstance(token_boxes, dict) else []:
            self._draw_rect(painter, rect, scale_x, scale_y, QColor(14, 165, 233), 2, 60)

        painter.end()
        return pixmap

    @staticmethod
    def _draw_rect(
        painter: QPainter,
        rect: Optional[Tuple[float, float, float, float]],
        scale_x: float,
        scale_y: float,
        color: QColor,
        pen_width: int,
        fill_alpha: int,
    ) -> None:
        if rect is None:
            return
        x0, y0, x1, y1 = rect
        width = max(0.0, x1 - x0)
        height = max(0.0, y1 - y0)
        if width <= 0.0 or height <= 0.0:
            return
        q_rect = QRectF(x0 * scale_x, y0 * scale_y, width * scale_x, height * scale_y)
        fill_color = QColor(color)
        fill_color.setAlpha(max(0, min(255, fill_alpha)))
        painter.fillRect(q_rect, fill_color)
        pen = QPen(color)
        pen.setWidth(max(1, pen_width))
        painter.setPen(pen)
        painter.drawRect(q_rect)
