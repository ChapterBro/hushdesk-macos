"""Main application window for the HushDesk macOS client."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from PySide6.QtCore import Qt, Signal, Slot, QUrl
from PySide6.QtGui import (
    QAction,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QGuiApplication,
    QPalette,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from hushdesk.fs.exports import exports_dir, sanitize_filename, safe_write_text
from hushdesk.placeholders import build_placeholder_output
from hushdesk.pdf.mar_header import audit_date_from_filename
from hushdesk.pdf.mar_parser_mupdf import MarAuditResult, run_mar_audit
from hushdesk.preview.overlay import render_band_preview
from hushdesk.report.txt_writer import write_report
from hushdesk.workers.audit_worker import AuditWorker
from .evidence_panel import EvidencePanel
from .preview_dialog import PreviewDialog
from .review_explorer import ReviewExplorer


class _Chip(QFrame):
    """Simple chip-style widget displaying a label and a value."""

    def __init__(self, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Chip")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setStyleSheet(
            """
            QFrame#Chip {
                border-radius: 12px;
                background-color: #f2f2f7;
                padding: 6px 12px;
            }
            QFrame#Chip QLabel {
                color: #1c1c1e;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-size: 12px; font-weight: 500; text-transform: uppercase;")
        self.value_label = QLabel("0")
        self.value_label.setStyleSheet("font-size: 18px; font-weight: 600;")

        layout.addWidget(self.title_label, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.value_label, alignment=Qt.AlignmentFlag.AlignLeft)

    def set_value(self, value: int) -> None:
        self.value_label.setText(str(value))


class _DropArea(QFrame):
    """Drag-and-drop zone for MAR PDF selection."""

    file_dropped = Signal(Path)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setObjectName("DropArea")
        self.setStyleSheet(
            """
            QFrame#DropArea {
                border: 2px dashed #8e8e93;
                border-radius: 12px;
                background-color: #ffffff;
            }
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        self.title = QLabel("Drag MAR PDF here")
        self.subtitle = QLabel("or use the Browse button")
        self.subtitle.setStyleSheet("color: #8e8e93; font-size: 12px;")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            urls = [url for url in event.mimeData().urls() if url.isLocalFile()]
            if urls and urls[0].toLocalFile().lower().endswith(".pdf"):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        urls = [url for url in event.mimeData().urls() if url.isLocalFile()]
        if not urls:
            event.ignore()
            return
        pdf_path = Path(urls[0].toLocalFile())
        if pdf_path.suffix.lower() == ".pdf":
            event.acceptProposedAction()
            self.file_dropped.emit(pdf_path)
        else:
            event.ignore()


class MainWindow(QMainWindow):
    """Main window assembly for HushDesk."""

    SETTINGS_FILENAME = "settings.json"
    COUNT_KEYS = [
        ("Reviewed", "reviewed"),
        ("Hold-Miss", "hold_miss"),
        ("Held-Appropriate", "held_appropriate"),
        ("Compliant", "compliant"),
        ("DC'D", "dcd"),
    ]

    def __init__(self, app_support_dir: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("HushDesk — BP Audit")
        self.resize(960, 640)

        self._app_support_dir = app_support_dir
        self._settings_path = self._app_support_dir / self.SETTINGS_FILENAME
        self._selected_pdf: Optional[Path] = None
        self.selected_pdf: Optional[Path] = None
        self._thread: Optional[QThread] = None
        self._worker: Optional[AuditWorker] = None
        self._audit_completed = False
        self._total_bands = 0
        self._no_data_for_date = False
        self._active_toasts: list[QMessageBox] = []
        self._header_text_color = "#E5E7EB"
        self._header_muted_color = "#9CA3AF"
        self._latest_counts = {key: 0 for _, key in self.COUNT_KEYS}
        self._last_saved_log: Optional[str] = None
        self._audit_date_pending = True
        self._current_pdf_path: Optional[Path] = None
        self._qa_mode_enabled = False
        self.qa_action: Optional[QAction] = None
        self._records_payload: list[dict] = []
        self._anomalies_payload: list[dict] = []
        self._selected_record: Optional[dict] = None
        self._logs_path = (self._app_support_dir / "logs" / "gui_last_run.log")

        self._exports_dir = exports_dir()
        self._export_target_path = self._exports_dir
        self._latest_hall = "UNKNOWN"
        self._latest_audit_label = ""
        self._latest_audit_mmddyyyy = ""
        self._last_report_path: Optional[Path] = None
        self._open_exports_widget: Optional[QLabel] = None
        self._open_exports_widget_action: Optional[QWidgetAction] = None

        self._refresh_header_colors()
        palette_changed = getattr(QGuiApplication, "paletteChanged", None)
        if callable(getattr(palette_changed, "connect", None)):
            palette_changed.connect(self._refresh_header_colors)
        self._load_settings()
        self._build_ui()
        self._create_actions()

    # --- UI assembly -----------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget(self)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(24, 24, 24, 24)
        central_layout.setSpacing(18)

        header_frame = QFrame()
        header_layout = QGridLayout(header_frame)
        header_layout.setContentsMargins(12, 12, 12, 12)
        header_layout.setHorizontalSpacing(16)
        header_layout.setVerticalSpacing(8)
        header_layout.setColumnStretch(1, 1)

        self.source_label = QLabel("Source: —")
        self.source_label.setObjectName("SourceLabel")
        self.source_label.setStyleSheet(
            f"font-size: 14px; font-weight: 500; color: {self._header_text_color};"
        )

        self.audit_date_label = QLabel()
        self.audit_date_label.setObjectName("AuditDateLabel")
        self._set_audit_date_pending_label()

        self.drop_area = _DropArea()
        self.drop_area.setMinimumHeight(120)
        self.drop_area.file_dropped.connect(self._on_pdf_selected)

        self.browse_button = QPushButton("Browse…")
        self.browse_button.clicked.connect(self._browse_for_pdf)

        self.run_button = QPushButton("Run Audit")
        self.run_button.setEnabled(False)
        self.run_button.clicked.connect(self._start_audit)
        self.run_button.setStyleSheet(
            """
            QPushButton {
                background-color: #2563EB;
                color: #F9FAFB;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:disabled {
                background-color: #1f2937;
                color: #9CA3AF;
            }
            """
        )

        header_layout.addWidget(self.source_label, 0, 0, 1, 2)
        header_layout.addWidget(self.run_button, 0, 2, 1, 1)
        header_layout.addWidget(self.audit_date_label, 1, 0, 1, 3)
        header_layout.addWidget(self.drop_area, 2, 0, 1, 2)

        export_controls = QVBoxLayout()
        export_controls.setContentsMargins(0, 0, 0, 0)
        export_controls.setSpacing(6)
        export_controls.addWidget(self.browse_button)

        self.export_target_label = QLabel()
        self.export_target_label.setObjectName("ExportTargetLabel")
        self.export_target_label.setStyleSheet("color: #6B7280; font-size: 12px;")
        self.export_target_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        export_controls.addWidget(self.export_target_label)
        export_controls.addStretch(1)

        header_layout.addLayout(export_controls, 2, 2, 1, 1)
        self._set_export_target(self._export_target_path)

        self.status_banner = QLabel()
        self.status_banner.setObjectName("StatusBanner")
        self.status_banner.setWordWrap(True)
        self.status_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_banner.setTextFormat(Qt.TextFormat.RichText)
        self.status_banner.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.status_banner.setStyleSheet(
            """
            QLabel#StatusBanner {
                background-color: #fff4c2;
                border: 1px solid #ffd166;
                border-radius: 8px;
                padding: 8px 12px;
                color: #5c4400;
                font-weight: 500;
            }
            QLabel#StatusBanner a {
                color: #1d4ed8;
                text-decoration: underline;
            }
            """
        )
        self.status_banner.linkActivated.connect(self._on_status_link_activated)
        self.status_banner.hide()

        progress_frame = QFrame()
        progress_layout = QVBoxLayout(progress_frame)
        progress_layout.setContentsMargins(12, 12, 12, 12)
        progress_layout.setSpacing(8)

        self.progress_label = QLabel("Band —")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar)

        chips_frame = QFrame()
        chips_layout = QHBoxLayout(chips_frame)
        chips_layout.setContentsMargins(12, 12, 12, 12)
        chips_layout.setSpacing(12)

        self._chips: dict[str, _Chip] = {}
        self._chips_by_key: dict[str, _Chip] = {}
        for title, key in self.COUNT_KEYS:
            chip = _Chip(title)
            chips_layout.addWidget(chip)
            self._chips[title] = chip
            self._chips_by_key[key] = chip

        chips_layout.addStretch(1)

        self.review_explorer = ReviewExplorer()
        self.review_explorer.record_selected.connect(self._on_review_record_selected)
        self.review_explorer.anomaly_selected.connect(self._on_anomaly_selected)
        self.review_explorer.preview_requested.connect(self._on_preview_requested)

        self.evidence_panel = EvidencePanel()

        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        top_splitter.addWidget(self.review_explorer)
        top_splitter.addWidget(self.evidence_panel)
        top_splitter.setStretchFactor(0, 1)
        top_splitter.setStretchFactor(1, 2)

        self.log_panel = QPlainTextEdit()
        self.log_panel.setObjectName("LogPanel")
        self.log_panel.setReadOnly(True)
        self.log_panel.setPlaceholderText("Audit log will appear here.")

        content_splitter = QSplitter(Qt.Orientation.Vertical)
        content_splitter.addWidget(top_splitter)
        content_splitter.addWidget(self.log_panel)
        content_splitter.setStretchFactor(0, 3)
        content_splitter.setStretchFactor(1, 1)

        central_layout.addWidget(header_frame)
        central_layout.addWidget(self.status_banner)
        central_layout.addWidget(progress_frame)
        central_layout.addWidget(chips_frame)
        central_layout.addWidget(content_splitter, stretch=1)

        self.setCentralWidget(central)
        self._refresh_header_colors()

    def _create_actions(self) -> None:
        toolbar = self.addToolBar("Actions")
        toolbar.setMovable(False)

        self.copy_action = QAction("Copy Checklist", self)
        self.copy_action.setEnabled(False)
        self.copy_action.triggered.connect(self._copy_placeholder_checklist)

        self.save_action = QAction("Save TXT", self)
        self.save_action.setEnabled(False)
        self.save_action.triggered.connect(self._save_audit_txt)

        toolbar.addAction(self.copy_action)
        toolbar.addAction(self.save_action)
        self._add_export_toolbar_link(toolbar)

        self.qa_action = QAction("QA Mode", self)
        self.qa_action.setCheckable(True)
        self.qa_action.setToolTip("Toggle inline QA diagnostics in Results")
        self.qa_action.toggled.connect(self._on_qa_action_toggled)
        toolbar.addSeparator()
        toolbar.addAction(self.qa_action)

    # --- Appearance helpers --------------------------------------------------

    def _add_export_toolbar_link(self, toolbar) -> None:
        link_label = QLabel("<a href='#exports'>Open Export Folder</a>")
        link_label.setObjectName("OpenExportsLink")
        link_label.setTextFormat(Qt.TextFormat.RichText)
        link_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        link_label.linkActivated.connect(self._on_status_link_activated)
        link_label.setStyleSheet("font-size: 12px; margin-left: 8px;")

        action = QWidgetAction(self)
        action.setDefaultWidget(link_label)
        toolbar.addAction(action)

        self._open_exports_widget = link_label
        self._open_exports_widget_action = action

    def _set_export_target(self, path: Path) -> None:
        resolved = Path(path)
        try:
            resolved = resolved.expanduser()
        except OSError:
            resolved = resolved
        self._export_target_path = resolved
        self._update_export_target_label(resolved)

    def _update_export_target_label(self, path: Path) -> None:
        if not hasattr(self, "export_target_label"):
            return
        display = self._format_path_for_display(path)
        if path == self._exports_dir:
            text = f"Export target: Exports ({display})"
        else:
            text = f"Export target: {display}"
        self.export_target_label.setText(text)
        self.export_target_label.setToolTip(str(path))

    @staticmethod
    def _format_path_for_display(path: Path) -> str:
        try:
            path_str = str(path)
        except OSError:
            return str(path)
        home = str(Path.home())
        if path_str.startswith(home):
            suffix = path_str[len(home) :].lstrip("/")
            return f"~/{suffix}" if suffix else "~"
        return path_str

    @staticmethod
    def _norm_pdf(path: str | Path) -> Path:
        return Path(path).expanduser().resolve(strict=True)

    def _open_export_folder(self) -> None:
        target = self._export_target_path if self._export_target_path else self._exports_dir
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError:
            target = self._exports_dir
            target.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _open_logs_file(self) -> None:
        log_path = self._logs_path
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.touch(exist_ok=True)
        except OSError:
            return
        try:
            subprocess.Popen(["open", "-a", "TextEdit", str(log_path)])
        except Exception:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_path)))

    def _on_status_link_activated(self, link: str) -> None:
        if link == "#open-logs":
            self._open_logs_file()
            return
        self._open_export_folder()

    def _show_export_fallback_banner(self) -> None:
        message = "Saved to Exports (TCC) – <a href='#exports'>[Open Exports]</a>"
        self.status_banner.setText(message)
        self.status_banner.show()

    def _suggest_export_filename(self) -> str:
        stem = self._selected_pdf.stem if self._selected_pdf else "HushDesk"
        date_token = self._latest_audit_mmddyyyy.replace("/", "-") if self._latest_audit_mmddyyyy else "pending"
        hall_token = (self._latest_hall or "UNKNOWN").upper()
        base = f"{stem}__{date_token}__{hall_token}.txt"
        return sanitize_filename(base)

    def _current_report_text(self) -> Optional[str]:
        if self._last_report_path and self._last_report_path.exists():
            try:
                return self._last_report_path.read_text(encoding="utf-8")
            except OSError:
                pass
        if self._selected_pdf:
            return build_placeholder_output(self._selected_pdf)
        return None

    def _refresh_header_colors(self, palette: Optional[QPalette] = None) -> None:
        palette_obj = palette or QGuiApplication.palette()
        active_text = palette_obj.color(QPalette.Active, QPalette.WindowText)
        disabled_text = palette_obj.color(QPalette.Disabled, QPalette.WindowText)
        if active_text == disabled_text:
            disabled_text = active_text.lighter(150)
        self._header_text_color = active_text.name()
        self._header_muted_color = disabled_text.name()
        self._apply_header_styles()

    def _apply_header_styles(self) -> None:
        if hasattr(self, "source_label"):
            self.source_label.setStyleSheet(
                f"font-size: 14px; font-weight: 500; color: {self._header_text_color};"
            )
        if hasattr(self, "audit_date_label"):
            color = self._header_text_color if not self._audit_date_pending else self._header_muted_color
            self.audit_date_label.setStyleSheet(
                f"font-size: 14px; font-weight: 500; color: {color};"
            )

    # --- Settings -------------------------------------------------------------------

    def _load_settings(self) -> None:
        self._settings: dict[str, str] = {}
        if not self._settings_path.exists():
            return
        try:
            self._settings = json.loads(self._settings_path.read_text())
        except json.JSONDecodeError:
            # Corrupted settings should be ignored but not fatal
            self._settings = {}

    def _save_settings(self) -> None:
        try:
            self._settings_path.write_text(json.dumps(self._settings, indent=2))
        except OSError as exc:
            QMessageBox.warning(self, "Settings Error", f"Unable to persist settings: {exc}")

    # --- Actions --------------------------------------------------------------------

    def _browse_for_pdf(self) -> None:
        start_dir = self._settings.get("last_open_dir", str(Path.home()))
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select MAR PDF",
            start_dir,
            "PDF Files (*.pdf)",
        )
        if filename:
            self._on_pdf_selected(Path(filename))

    def _on_pdf_selected(self, pdf_path: Path) -> None:
        absolute_path = pdf_path.resolve()
        self._selected_pdf = absolute_path
        self.selected_pdf = absolute_path
        self.drop_area.title.setText(absolute_path.name)
        self.drop_area.subtitle.setText(str(absolute_path.parent))
        self.source_label.setText(f"Source: {absolute_path.name}")
        self._set_audit_date_pending_label()
        self.run_button.setEnabled(True)
        self._audit_completed = False
        self.copy_action.setEnabled(False)
        self.save_action.setEnabled(False)
        self.log_panel.setPlainText("Ready to audit placeholder MAR.")
        self._reset_progress()
        self._settings["last_open_dir"] = str(absolute_path.parent)
        self._save_settings()

    def _set_band_progress_label(self, current: Optional[int], total: Optional[int]) -> None:
        if isinstance(total, int) and total > 0 and isinstance(current, int):
            clamped_current = max(0, min(current, total))
            self.progress_label.setText(f"Band {clamped_current} of {total}")
            self._total_bands = total
        else:
            self.progress_label.setText("Band —")
            self._total_bands = 0

    def _update_band_progress_from_stats(self, stats: MarAuditResult) -> None:
        instrumentation = stats.instrumentation if isinstance(stats.instrumentation, dict) else {}
        pages_total: Optional[int] = None
        if isinstance(instrumentation, dict):
            try:
                pages_value = instrumentation.get("pages")
                if pages_value is not None:
                    pages_total = int(pages_value)
            except (TypeError, ValueError):
                pages_total = None

        page_indices: set[int] = set()
        for record in getattr(stats, "due_records", []):
            page_index = getattr(record, "page_index", None)
            if isinstance(page_index, int):
                page_indices.add(page_index)
        pages_with_band: Optional[int] = len(page_indices) if page_indices else None

        if pages_total is None and pages_with_band is not None:
            pages_total = pages_with_band
        if pages_with_band is None and isinstance(pages_total, int) and pages_total >= 0:
            pages_with_band = pages_total

        self._set_band_progress_label(pages_with_band, pages_total)

    def _reset_progress(self) -> None:
        self._set_band_progress_label(None, None)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self._set_audit_date_pending_label()
        self.status_banner.hide()
        self._no_data_for_date = False
        self._last_report_path = None
        self._set_export_target(self._exports_dir)
        self._latest_audit_mmddyyyy = ""
        self._latest_hall = "UNKNOWN"
        for key in self._latest_counts:
            self._latest_counts[key] = 0
        for chip in self._chips.values():
            chip.set_value(0)
        self._records_payload.clear()
        self._selected_record = None
        self._current_pdf_path = None
        self._anomalies_payload.clear()
        if hasattr(self, "review_explorer"):
            self.review_explorer.clear()
            self.review_explorer.update_anomalies([])
            self.review_explorer.clear_anomaly_filter()
        self._set_qa_mode(False)
        if hasattr(self, "evidence_panel"):
            self.evidence_panel.clear()
        self.log_panel.moveCursor(QTextCursor.MoveOperation.End)

    def _start_audit(self) -> None:
        if not self._selected_pdf:
            return

        try:
            pdf_path = self._norm_pdf(self._selected_pdf)
        except Exception as exc:
            self._handle_audit_error(exc)
            return

        try:
            import fitz  # type: ignore
        except ImportError as exc:
            self._handle_audit_error(exc)
            return

        try:
            with fitz.open(pdf_path) as _doc:  # type: ignore[attr-defined]
                pass
        except Exception as exc:
            self._handle_audit_error(exc)
            return

        self._selected_pdf = pdf_path
        self._worker = None
        self._thread = None
        self._last_saved_log = None
        self._audit_completed = False
        self._no_data_for_date = False
        self.status_banner.hide()
        self.run_button.setEnabled(False)
        self.copy_action.setEnabled(False)
        self.save_action.setEnabled(False)

        self._reset_progress()
        self.log_panel.setPlainText("Running MAR audit…")
        self._append_log_line(f"Started audit: {pdf_path}")
        self._write_gui_log_entry(f"Started audit: {pdf_path}")

        hall = self._latest_hall or "UNKNOWN"

        qa_enabled = bool(self._qa_mode_enabled)
        qa_prefix = None if qa_enabled else False

        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            audit_dt, audit_disp = audit_date_from_filename(str(pdf_path))
            stats = run_mar_audit(str(pdf_path), hall, audit_dt, qa_prefix=qa_prefix)
        except Exception as exc:
            self._handle_audit_error(exc)
            return
        finally:
            QGuiApplication.restoreOverrideCursor()

        self._handle_audit_success(pdf_path, audit_disp, stats)

    def _handle_audit_success(self, pdf_path: Path, audit_display: str, stats: MarAuditResult) -> None:
        counts = {str(key): int(value) for key, value in stats.counts.items()}
        hold_miss = counts.get("hold_miss", 0)
        held_app = counts.get("held_appropriate", 0)
        compliant = counts.get("compliant", 0)
        dcd = counts.get("dcd", 0)
        counts["reviewed"] = hold_miss + held_app + compliant + dcd
        self._on_summary_counts(counts)
        date_token = audit_display.split("—", 1)[0].strip() if audit_display else ""
        if not date_token or date_token.lower().startswith("audit"):
            date_token = stats.audit_date_mmddyyyy or "unknown"
        summary_line = (
            f"Blocks:{stats.blocks} Tracks:{stats.tracks} Date:{date_token} "
            f"Reviewed:{counts.get('reviewed', 0)} Hold-Miss:{hold_miss} "
            f"Held-Appropriate:{held_app} Compliant:{compliant} DC'D:{dcd}"
        )
        self._append_log_line(summary_line)
        print(summary_line, flush=True)
        self._write_gui_log_entry(summary_line)

        records_payload = [
            AuditWorker._record_payload(index, record)
            for index, record in enumerate(stats.records)
        ]
        payload = {
            "counts": counts,
            "records": records_payload,
            "anomalies": [],
            "source_pdf": str(pdf_path),
            "hall": stats.hall,
            "audit_date_text": stats.audit_date_mmddyyyy,
            "qa_paths": [str(path) for path in stats.qa_paths],
            "summary_line": stats.summary_line,
            "blocks": stats.blocks,
            "tracks": stats.tracks,
            "instrumentation": dict(stats.instrumentation),
            "instrument_line": stats.instrument_line,
        }
        self._on_summary_payload(payload)

        label_value = f"{audit_display} — Central"
        self._on_audit_date_text(label_value)

        if not stats.records:
            self._on_no_data_for_date()

        export_dir = self._exports_dir
        export_dir.mkdir(parents=True, exist_ok=True)
        base_name = Path(stats.source_basename).stem
        report_name = sanitize_filename(
            f"{stats.audit_date_mmddyyyy}_{stats.hall}_{base_name}.txt"
        )
        report_path = export_dir / report_name
        report_path = write_report(
            records=stats.records,
            counts=counts,
            audit_date_mmddyyyy=stats.audit_date_mmddyyyy,
            hall=stats.hall,
            source_basename=stats.source_basename,
            out_path=report_path,
        )

        if stats.instrument_line:
            self._on_worker_log(stats.instrument_line)
            self._write_gui_log_entry(stats.instrument_line)
        if stats.summary_line:
            self._on_worker_log(stats.summary_line)
            self._write_gui_log_entry(stats.summary_line)

        if stats.qa_paths:
            qa_line = (
                f"QA overlays saved ({len(stats.qa_paths)}) to "
                f"{stats.qa_paths[0].parent}"
            )
            self._on_worker_log(qa_line)
            self._write_gui_log_entry(qa_line)

        saved_line = f"Report saved: {report_path}"
        self._on_worker_log(saved_line)
        self._write_gui_log_entry(saved_line)

        self._on_worker_saved(str(report_path))
        self._on_audit_finished(report_path)

        self._update_band_progress_from_stats(stats)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.status_banner.hide()

        ok_line = (
            f'GUI_AUDIT_OK source="{pdf_path}" '
            f"reviewed={counts.get('reviewed', 0)} "
            f"hm={hold_miss} ha={held_app} comp={compliant} dcd={dcd}"
        )
        self._append_log_line(ok_line)
        print(ok_line, flush=True)
        self._write_gui_log_entry(ok_line)
        self._automation_compare_headless(counts)

    def _automation_compare_headless(self, counts: dict[str, int]) -> None:
        if os.environ.get("HUSHDESK_AUTOMATION") != "1":
            return
        cache_path = self._logs_path.parent / "last_headless.json"
        try:
            raw = cache_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return
        except OSError:
            return
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return

        counts_obj = payload.get("counts") if isinstance(payload, dict) else None
        if counts_obj is None and isinstance(payload, dict):
            counts_obj = payload
        if not isinstance(counts_obj, dict):
            return

        keys = ("reviewed", "hold_miss", "held_appropriate", "compliant", "dcd")
        try:
            expected = {key: int(counts_obj[key]) for key in keys}
        except (KeyError, TypeError, ValueError):
            return
        gui_counts = {key: int(counts.get(key, 0)) for key in keys}
        if all(gui_counts[key] == expected[key] for key in keys):
            message = "GUI_HEADLESS_COMPARE ok"
        else:
            message = f"GUI_HEADLESS_COMPARE mismatch gui={gui_counts} expected={expected}"
        print(message, flush=True)
        self._write_gui_log_entry(message)

    def _handle_audit_error(self, exc: Exception) -> None:
        error_name = exc.__class__.__name__
        message_text = " ".join(str(exc).split())
        detail = f"{error_name}: {message_text}" if message_text else error_name
        safe_detail = detail.replace('"', "'")
        banner_text = f"MAR parser error: {safe_detail}"
        truncated = banner_text if len(banner_text) <= 120 else f"{banner_text[:117]}…"
        banner_line = f"{truncated} — <a href='#open-logs'>Open Logs</a>"
        self.status_banner.setText(banner_line)
        self.status_banner.show()

        fail_line = f'GUI_AUDIT_FAIL error="{safe_detail}"'
        self._append_log_line(fail_line)
        print(fail_line, flush=True)
        self._write_gui_log_entry(fail_line, exc=exc)

        self.run_button.setEnabled(True)
        self.copy_action.setEnabled(False)
        self.save_action.setEnabled(False)
        self._set_band_progress_label(None, None)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self._audit_completed = False

    def _write_gui_log_entry(self, line: str, exc: Optional[BaseException] = None) -> None:
        log_path = self._logs_path
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            return
        try:
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(f"[{datetime.now().isoformat()}] {line}\n")
                if exc is not None:
                    handle.write(
                        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
                    )
                    handle.write("\n")
        except OSError:
            pass

    @Slot(str)
    def _on_run_started(self, input_path: str) -> None:
        self.log_panel.clear()
        self._reset_progress()
        self._last_saved_log = None
        self._append_log_line(f"Started audit: {input_path}")

    @Slot(int, int)
    def _on_progress_changed(self, current: int, total: int) -> None:
        self._set_band_progress_label(current, total)
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(current)

    @Slot(dict)
    def _on_summary_counts(self, counts: dict) -> None:
        for title, key in self.COUNT_KEYS:
            value = int(counts.get(key, 0))
            self._latest_counts[key] = value
            chip = self._chips_by_key.get(key)
            if chip:
                chip.set_value(value)

    @Slot(dict)
    def _on_summary_payload(self, payload: dict) -> None:
        counts_obj = payload.get("counts") if isinstance(payload, dict) else {}
        records_obj = payload.get("records") if isinstance(payload, dict) else []
        anomalies_obj = payload.get("anomalies") if isinstance(payload, dict) else []
        source_pdf = payload.get("source_pdf") if isinstance(payload, dict) else None
        hall_value = payload.get("hall") if isinstance(payload, dict) else None
        audit_text = payload.get("audit_date_text") if isinstance(payload, dict) else None
        if isinstance(hall_value, str):
            self._latest_hall = (hall_value or "UNKNOWN").upper()
        if isinstance(audit_text, str):
            self._latest_audit_mmddyyyy = audit_text.strip()
        if isinstance(source_pdf, str):
            try:
                self._current_pdf_path = Path(source_pdf).resolve()
            except OSError:
                self._current_pdf_path = Path(source_pdf)
        else:
            self._current_pdf_path = None
        counts_dict: dict[str, int] = {}
        if isinstance(counts_obj, dict):
            for key, value in counts_obj.items():
                try:
                    counts_dict[str(key)] = int(value)
                except (TypeError, ValueError):
                    continue
        if isinstance(records_obj, list):
            self._records_payload = [
                dict(record) for record in records_obj if isinstance(record, dict)
            ]
        else:
            self._records_payload = []
        if isinstance(anomalies_obj, list):
            self._anomalies_payload = [
                dict(entry) for entry in anomalies_obj if isinstance(entry, dict)
            ]
        else:
            self._anomalies_payload = []
        if hasattr(self, "review_explorer"):
            self.review_explorer.update_records(counts=counts_dict, records=self._records_payload)
            self.review_explorer.update_anomalies(self._anomalies_payload)
            self.review_explorer.set_qa_mode(self._qa_mode_enabled)
        if hasattr(self, "evidence_panel"):
            if self._records_payload:
                self.evidence_panel.clear("Select a decision to view details.")
            else:
                self.evidence_panel.clear("No decisions available.")

    @Slot(dict)
    def _on_review_record_selected(self, payload: dict) -> None:
        self._selected_record = dict(payload)
        if hasattr(self, "evidence_panel"):
            self.evidence_panel.set_record(self._selected_record, self._current_pdf_path)

    @Slot(dict)
    def _on_preview_requested(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        if self._current_pdf_path is None or not self._current_pdf_path.exists():
            QMessageBox.warning(self, "Preview Unavailable", "PDF source not available for preview.")
            return
        page_index: Optional[int] = payload.get("page_index") if isinstance(payload.get("page_index"), int) else None
        if page_index is None:
            extras = payload.get("extras") if isinstance(payload.get("extras"), dict) else {}
            maybe_page = extras.get("page_index")
            if isinstance(maybe_page, int):
                page_index = maybe_page
        if page_index is None:
            QMessageBox.warning(self, "Preview Unavailable", "Record is missing page information.")
            return

        label_list = payload.get("overlay_labels") if isinstance(payload.get("overlay_labels"), list) else []
        overlays = {
            "page_pixels": payload.get("page_pixels") if isinstance(payload.get("page_pixels"), dict) else {},
            "audit_band": payload.get("audit_band"),
            "slot_bboxes": payload.get("slot_bboxes") if isinstance(payload.get("slot_bboxes"), dict) else {},
            "vital_bbox": payload.get("vital_bbox"),
            "mark_bboxes": payload.get("mark_bboxes") if isinstance(payload.get("mark_bboxes"), list) else [],
            "labels": label_list,
            "overlay_labels": label_list,
        }

        temp_dir = Path(tempfile.gettempdir())
        preview_path = temp_dir / f"hushdesk-preview-{uuid4().hex}.png"
        try:
            render_band_preview(
                str(self._current_pdf_path),
                int(page_index),
                overlays,
                preview_path,
            )
        except Exception as exc:  # pragma: no cover - user feedback
            QMessageBox.warning(self, "Preview Error", f"Unable to render preview: {exc}")
            return

        dialog = PreviewDialog(preview_path, overlays, self)
        dialog.exec()

    @Slot(dict)
    def _on_anomaly_selected(self, anomaly: dict) -> None:
        if not isinstance(anomaly, dict):
            return
        if hasattr(self, "review_explorer"):
            self.review_explorer.apply_anomaly_filter(anomaly)

    @Slot(bool)
    def _on_qa_action_toggled(self, checked: bool) -> None:
        self._set_qa_mode(bool(checked), sync_action=False)

    def _set_qa_mode(self, enabled: bool, *, sync_action: bool = True) -> None:
        if sync_action and self.qa_action is not None:
            self.qa_action.blockSignals(True)
            self.qa_action.setChecked(enabled)
            self.qa_action.blockSignals(False)
        if self._qa_mode_enabled == enabled:
            return
        self._qa_mode_enabled = bool(enabled)
        if hasattr(self, "review_explorer"):
            self.review_explorer.set_qa_mode(self._qa_mode_enabled)
            if not self._qa_mode_enabled:
                self.review_explorer.clear_anomaly_filter()

    @Slot(str)
    def _on_worker_log(self, message: str) -> None:
        self._append_log_line(message)
        if "Permission denied writing to" in message:
            self._show_export_fallback_banner()

    @Slot(str)
    def _on_worker_saved(self, path: str) -> None:
        try:
            final_path = Path(path).expanduser()
        except (OSError, TypeError):
            final_path = Path(path)
        self._last_report_path = final_path
        self._set_export_target(final_path.parent)
        self._dismiss_toasts_with_title("Saved")
        short_path = self._format_path_for_display(final_path)
        self._show_toast("Saved", f"Saved to {short_path}")
        summary_parts = " · ".join(
            f"{title}: {self._latest_counts[key]}" for title, key in self.COUNT_KEYS
        )
        saved_message = f"TXT saved to {final_path} — {summary_parts}"
        if saved_message != self._last_saved_log:
            self._append_log_line(saved_message)
            self._last_saved_log = saved_message
        if self.status_banner.isVisible():
            self.status_banner.hide()

    @Slot(str)
    def _on_worker_warning(self, message: str) -> None:
        self.status_banner.setText(message)
        self.status_banner.show()
        self._append_log_line(f"Warning: {message}")

    @Slot(Path)
    def _on_audit_finished(self, output_path: Path) -> None:
        self._audit_completed = True
        self.run_button.setEnabled(True)
        self.copy_action.setEnabled(True)
        self.save_action.setEnabled(True)
        if self._no_data_for_date:
            self._append_log_line("No data for selected date.")
        else:
            self._append_log_line("Audit complete.")
        self._settings["last_output_directory"] = str(output_path.parent)
        self._save_settings()
        self._worker = None

    def _copy_placeholder_checklist(self) -> None:
        clipboard = QGuiApplication.clipboard()
        clipboard.setText("HushDesk BP audit checklist placeholder.")
        QMessageBox.information(self, "Copy Checklist", "Placeholder checklist copied to clipboard.")

    def _save_audit_txt(self) -> None:
        if not self._selected_pdf:
            QMessageBox.warning(self, "No PDF", "Select a MAR PDF before saving output.")
            return
        if not self._audit_completed and not self._last_report_path:
            QMessageBox.warning(self, "Audit Incomplete", "Run the audit before saving output.")
            return

        report_text = self._current_report_text()
        if report_text is None:
            QMessageBox.warning(self, "Nothing to Save", "No audit results are available to save.")
            return

        suggested_name = self._suggest_export_filename()
        default_dir = self._settings.get("last_manual_save_dir") or str(self._export_target_path)
        try:
            default_base = Path(default_dir).expanduser()
        except OSError:
            default_base = self._exports_dir
        default_base.mkdir(parents=True, exist_ok=True)
        default_path = default_base / suggested_name

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Audit TXT",
            str(default_path),
            "Text Files (*.txt)",
        )

        if not filename:
            fallback_path = self._exports_dir / suggested_name
            final_path = safe_write_text(fallback_path, report_text)
            self._last_report_path = final_path
            self._set_export_target(final_path.parent)
            self._dismiss_toasts_with_title("Saved")
            self._show_toast("Saved", "Saved to Exports (TCC fallback)")
            self._show_export_fallback_banner()
            summary_parts = " · ".join(
                f"{title}: {self._latest_counts[key]}" for title, key in self.COUNT_KEYS
            )
            saved_message = f"TXT saved to {final_path} — {summary_parts}"
            self._append_log_line(saved_message)
            self._settings["last_output_directory"] = str(final_path.parent)
            self._save_settings()
            self._last_saved_log = saved_message
            return

        target_path = Path(filename).expanduser()
        sanitized_name = sanitize_filename(target_path.name or suggested_name)
        target_path = target_path.with_name(sanitized_name)
        self._settings["last_manual_save_dir"] = str(target_path.parent)
        self._settings["last_output_directory"] = str(target_path.parent)
        self._save_settings()

        final_path = safe_write_text(target_path, report_text)
        self._last_report_path = final_path
        self._set_export_target(final_path.parent)
        self._dismiss_toasts_with_title("Saved")
        if final_path != target_path:
            self._show_toast("Saved", "Saved to Exports (TCC fallback)")
            self._show_export_fallback_banner()
        else:
            short_final = self._format_path_for_display(final_path)
            self._show_toast("Saved", f"Saved to {short_final}")
            if self.status_banner.isVisible():
                self.status_banner.hide()
        summary_parts = " · ".join(
            f"{title}: {self._latest_counts[key]}" for title, key in self.COUNT_KEYS
        )
        saved_message = f"TXT saved to {final_path} — {summary_parts}"
        if saved_message != self._last_saved_log:
            self._append_log_line(saved_message)
            self._last_saved_log = saved_message

    @Slot(str)
    def _on_audit_date_text(self, label_value: str) -> None:
        self._audit_date_pending = False
        self.audit_date_label.setText(f"Audit Date: {label_value}")
        self._latest_audit_label = label_value
        dash_split = label_value.split("—", 1)
        if dash_split:
            candidate = dash_split[0].strip()
            if candidate:
                self._latest_audit_mmddyyyy = candidate
        self._apply_header_styles()

    @Slot()
    def _on_no_data_for_date(self) -> None:
        self._no_data_for_date = True
        self.status_banner.setText("No data for selected date")
        self.status_banner.show()
        self._append_log_line("No data for selected date.")

    def _set_audit_date_pending_label(self) -> None:
        self._audit_date_pending = True
        self.audit_date_label.setText("Audit Date: (pending) — Central")
        self._apply_header_styles()

    def _append_log_line(self, message: str) -> None:
        if not message:
            return
        self.log_panel.appendPlainText(message)
        cursor = self.log_panel.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_panel.setTextCursor(cursor)

    def _dismiss_toasts_with_title(self, title: str) -> None:
        for toast in list(self._active_toasts):
            if toast.windowTitle() == title:
                toast.close()

    def _show_toast(self, title: str, message: str) -> None:
        toast = QMessageBox(self)
        toast.setWindowTitle(title)
        toast.setText(message)
        toast.setIcon(QMessageBox.Icon.Information)
        toast.setStandardButtons(QMessageBox.StandardButton.Ok)
        toast.setModal(False)
        toast.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        toast.finished.connect(lambda *_: self._active_toasts.remove(toast) if toast in self._active_toasts else None)
        self._active_toasts.append(toast)
        toast.open()

    def closeEvent(self, event) -> None:  # noqa: N802
        thread = self._thread
        if thread is not None:
            try:
                if thread.isRunning():
                    thread.quit()
                    thread.wait(1000)
            except RuntimeError:
                pass
        super().closeEvent(event)
