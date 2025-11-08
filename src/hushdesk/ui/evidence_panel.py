"""Evidence drawer showing rule context and PDF preview overlays."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QUrl, QRectF
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from hushdesk.ui.preview_renderer import (
    project_rect_list,
    qpixmap_from_fitz,
    rect_points_to_pixels,
    render_page_pixmap,
)
from hushdesk.ui.preview_view import PreviewView

try:  # pragma: no cover - optional dependency
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore


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
        self._preview_cache: Dict[Tuple[str, int], tuple[QPixmap, Optional[QRectF]]] = {}
        self._current_preview_pixmap: Optional[QPixmap] = None
        self._preview_scale_pct = 100
        self._fit_mode = "custom"
        self._region_rect: Optional[QRectF] = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Evidence")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(title)

        self.summary_label = QLabel("Select a decision to view details.")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.details_label = QLabel()
        self.details_label.setWordWrap(True)
        self.details_label.setStyleSheet("color: #374151;")
        layout.addWidget(self.details_label)

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

        layout.addLayout(button_row)

        self.preview_status = QLabel("Preview not generated.")
        self.preview_status.setStyleSheet("color: #6b7280; font-size: 12px;")
        layout.addWidget(self.preview_status)

        self.preview_view = PreviewView(self)
        self.preview_view.setStyleSheet("background-color: #f9fafb; border: 1px solid #e5e7eb;")
        layout.addWidget(self.preview_view, stretch=1)

    def clear(self, message: Optional[str] = None) -> None:
        self._record = None
        self._pdf_path = None
        self._current_preview_pixmap = None
        self._region_rect = None
        self.summary_label.setText(message or "Select a decision to view details.")
        self.details_label.clear()
        self.preview_view.clear()
        self.preview_status.setText("Preview not generated.")
        self.open_button.setEnabled(False)
        self.preview_button.setEnabled(False)

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
        self.preview_button.setEnabled(has_pdf and fitz is not None and page_index is not None)
        self.preview_status.setText("Preview not generated." if fitz is not None else "Preview requires PyMuPDF.")
        self.preview_view.clear()
        self._region_rect = None

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
        cache_key = (str(self._pdf_path), int(self._record.get("id", -1)))
        cached = self._preview_cache.get(cache_key)
        if cached is None:
            rendered = self._render_preview(self._record, self._pdf_path)
            if rendered is None:
                self.preview_status.setText("Unable to render preview.")
                return
            pixmap, region_rect = rendered
            self._preview_cache[cache_key] = (pixmap, region_rect)
        else:
            pixmap, region_rect = cached
        self._current_preview_pixmap = pixmap
        self._region_rect = region_rect
        self.preview_view.set_pixmap(pixmap)
        self._apply_preview_scale()
        page_index = self._extract_page_index(self._record) or 0
        self.preview_status.setText(f"Preview: page {page_index + 1}.")

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
        self._apply_preview_scale()

    def set_fit_mode(self, mode: str) -> str:
        valid = {"width", "height", "page", "region", "actual"}
        resolved = mode if mode in valid else "custom"
        if resolved == "region" and not self.has_region_roi():
            resolved = "page"
        self._fit_mode = resolved
        self._apply_preview_scale()
        return self._fit_mode

    def current_zoom_percent(self) -> int:
        return self._preview_scale_pct

    def has_region_roi(self) -> bool:
        return self._region_rect is not None and not self._region_rect.isNull()

    def _apply_preview_scale(self) -> None:
        pixmap = self._current_preview_pixmap
        if pixmap is None:
            self.preview_view.clear()
            return
        if self.preview_view.pixmap_item() is None:
            self.preview_view.set_pixmap(pixmap)
        self.preview_view.set_region_rect(self._region_rect)
        if self._fit_mode == "custom":
            scale = max(0.25, min(4.0, self._preview_scale_pct / 100.0))
            self.preview_view.set_custom_zoom(scale)
            return
        self.preview_view.set_fit_mode(self._fit_mode)

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

    def _render_preview(self, record: dict, pdf_path: Path) -> Optional[tuple[QPixmap, Optional[QRectF]]]:
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
                pixmap_obj, matrix = render_page_pixmap(doc, page_index)
        except Exception:  # pragma: no cover - defensive
            return None

        if isinstance(pixmap_obj, QPixmap):
            pixmap = pixmap_obj
        else:
            pixmap = qpixmap_from_fitz(pixmap_obj)  # type: ignore[arg-type]
        if pixmap.isNull():
            return None

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        token_boxes = extras.get("token_boxes") if isinstance(extras.get("token_boxes"), dict) else {}
        band_rect = rect_points_to_pixels(extras.get("band_rect"), matrix)
        slot_rect = rect_points_to_pixels(extras.get("slot_rect"), matrix)
        due_rect = rect_points_to_pixels(extras.get("due_rect"), matrix)

        self._draw_rect(painter, band_rect, QColor(37, 99, 235), 2, 30)
        self._draw_rect(painter, slot_rect, QColor(16, 185, 129), 3, 50)
        self._draw_rect(painter, due_rect, QColor(249, 115, 22), 3, 0)

        for rect in project_rect_list(token_boxes.get("bp", []), matrix):
            self._draw_rect(painter, rect, QColor(139, 92, 246), 2, 60)
        for rect in project_rect_list(token_boxes.get("hr", []), matrix):
            self._draw_rect(painter, rect, QColor(14, 165, 233), 2, 60)

        painter.end()
        region_tuple = slot_rect or band_rect
        region_rect = QRectF(*region_tuple) if region_tuple else None
        return pixmap, region_rect

    @staticmethod
    def _draw_rect(
        painter: QPainter,
        rect: Optional[Tuple[float, float, float, float]],
        color: QColor,
        pen_width: int,
        fill_alpha: int,
    ) -> None:
        if rect is None:
            return
        x, y, width, height = rect
        if width <= 0.0 or height <= 0.0:
            return
        q_rect = QRectF(x, y, width, height)
        fill_color = QColor(color)
        fill_color.setAlpha(max(0, min(255, fill_alpha)))
        painter.fillRect(q_rect, fill_color)
        pen = QPen(color)
        pen.setWidth(max(1, pen_width))
        painter.setPen(pen)
        painter.drawRect(q_rect)
