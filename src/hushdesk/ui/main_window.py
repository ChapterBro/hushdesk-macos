"""Main application window for the HushDesk macOS client."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Optional
from uuid import uuid4

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QGuiApplication, QPalette, QTextCursor
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
)

from hushdesk.placeholders import build_placeholder_output
from hushdesk.preview.overlay import render_band_preview
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
        ("Held-OK", "held_ok"),
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
        header_layout.addWidget(self.browse_button, 2, 2, 1, 1)

        self.status_banner = QLabel("No data for selected date")
        self.status_banner.setObjectName("StatusBanner")
        self.status_banner.setWordWrap(True)
        self.status_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
            """
        )
        self.status_banner.hide()

        progress_frame = QFrame()
        progress_layout = QVBoxLayout(progress_frame)
        progress_layout.setContentsMargins(12, 12, 12, 12)
        progress_layout.setSpacing(8)

        self.progress_label = QLabel("Band 0 of 0")
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
        self.save_action.triggered.connect(self._save_placeholder_txt)

        toolbar.addAction(self.copy_action)
        toolbar.addAction(self.save_action)

        self.qa_action = QAction("QA Mode", self)
        self.qa_action.setCheckable(True)
        self.qa_action.setToolTip("Toggle inline QA diagnostics in Results")
        self.qa_action.toggled.connect(self._on_qa_action_toggled)
        toolbar.addSeparator()
        toolbar.addAction(self.qa_action)

    # --- Appearance helpers --------------------------------------------------

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

    def _reset_progress(self) -> None:
        self._total_bands = 0
        self.progress_label.setText("Band 0 of 0")
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self._set_audit_date_pending_label()
        self.status_banner.hide()
        self._no_data_for_date = False
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

        self.run_button.setEnabled(False)
        self.log_panel.setPlainText("Preparing audit…")

        self._thread = QThread()
        worker = AuditWorker(input_pdf=self._selected_pdf, delay=0.25)
        worker.moveToThread(self._thread)
        self._worker = worker

        worker.started.connect(self._on_run_started)
        worker.progress.connect(self._on_progress_changed)
        worker.log.connect(self._on_worker_log)
        worker.saved.connect(self._on_worker_saved)
        worker.warning.connect(self._on_worker_warning)
        worker.audit_date_text.connect(self._on_audit_date_text)
        worker.summary_counts.connect(self._on_summary_counts)
        worker.summary_payload.connect(self._on_summary_payload)
        worker.no_data_for_date.connect(self._on_no_data_for_date)
        worker.finished.connect(self._on_audit_finished)
        worker.finished.connect(self._thread.quit)
        worker.finished.connect(worker.deleteLater)

        self._thread.started.connect(worker.run)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    @Slot(str)
    def _on_run_started(self, input_path: str) -> None:
        self.log_panel.clear()
        self._reset_progress()
        self._last_saved_log = None
        self._append_log_line(f"Started audit: {input_path}")

    @Slot(int, int)
    def _on_progress_changed(self, current: int, total: int) -> None:
        self._total_bands = total
        self.progress_label.setText(f"Band {current} of {total}")
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

    @Slot(str)
    def _on_worker_saved(self, path: str) -> None:
        self._dismiss_toasts_with_title("Saved")
        self._show_toast("Saved", f"Saved: {path}")
        summary_parts = " · ".join(
            f"{title}: {self._latest_counts[key]}" for title, key in self.COUNT_KEYS
        )
        saved_message = f"TXT saved to {path} — {summary_parts}"
        if saved_message != self._last_saved_log:
            self._append_log_line(saved_message)
            self._last_saved_log = saved_message

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

    def _save_placeholder_txt(self) -> None:
        if not self._selected_pdf:
            QMessageBox.warning(self, "No PDF", "Select a MAR PDF before saving output.")
            return
        if not self._audit_completed:
            QMessageBox.warning(self, "Audit Incomplete", "Run the audit before saving output.")
            return
        output_path = self._selected_pdf.with_suffix(".txt")
        try:
            output_path.write_text(build_placeholder_output(self._selected_pdf))
        except OSError as exc:
            QMessageBox.critical(self, "Save Error", f"Unable to save placeholder TXT: {exc}")
            return
        self._append_log_line(f"Placeholder TXT saved to {output_path}")
        self._settings["last_output_directory"] = str(output_path.parent)
        self._save_settings()
        QMessageBox.information(self, "Save TXT", f"Placeholder TXT saved to:\n{output_path}")

    @Slot(str)
    def _on_audit_date_text(self, label_value: str) -> None:
        self._audit_date_pending = False
        self.audit_date_label.setText(f"Audit Date: {label_value}")
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
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(1000)
        super().closeEvent(event)
