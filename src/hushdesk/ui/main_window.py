"""Main application window for the HushDesk macOS client."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QGuiApplication, QTextCursor
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
    QVBoxLayout,
    QWidget,
)

from hushdesk.placeholders import build_placeholder_output
from hushdesk.workers.audit_worker import AuditWorker


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

        self._chips = {
            "Reviewed": _Chip("Reviewed"),
            "Hold-Miss": _Chip("Hold-Miss"),
            "Held-OK": _Chip("Held-OK"),
            "Compliant": _Chip("Compliant"),
            "DC'D": _Chip("DC'D"),
        }

        for chip in self._chips.values():
            chips_layout.addWidget(chip)

        self.log_panel = QPlainTextEdit()
        self.log_panel.setObjectName("LogPanel")
        self.log_panel.setReadOnly(True)
        self.log_panel.setPlaceholderText("Audit log will appear here.")

        central_layout.addWidget(header_frame)
        central_layout.addWidget(self.status_banner)
        central_layout.addWidget(progress_frame)
        central_layout.addWidget(chips_frame)
        central_layout.addWidget(self.log_panel, stretch=1)

        self.setCentralWidget(central)

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
        for chip in self._chips.values():
            chip.set_value(0)
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
        self._append_log_line(f"Started audit: {input_path}")
        self._append_log_line("DEBUG: band progress total set to 0 (reset)")

    @Slot(int, int)
    def _on_progress_changed(self, current: int, total: int) -> None:
        self._total_bands = total
        self.progress_label.setText(f"Band {current} of {total}")
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(current)
        self._append_log_line(f"DEBUG: band progress tick current={current}, total={total}")

    @Slot(dict)
    def _on_summary_counts(self, counts: dict) -> None:
        self._chips["Reviewed"].set_value(int(counts.get("reviewed", 0)))
        self._chips["Hold-Miss"].set_value(int(counts.get("hold_miss", 0)))
        self._chips["Held-OK"].set_value(int(counts.get("held_ok", 0)))
        self._chips["Compliant"].set_value(int(counts.get("compliant", 0)))
        self._chips["DC'D"].set_value(int(counts.get("dcd", 0)))

    @Slot(str)
    def _on_worker_log(self, message: str) -> None:
        self._append_log_line(message)

    @Slot(str)
    def _on_worker_saved(self, path: str) -> None:
        self._append_log_line(f"Saved output: {path}")
        self._show_toast("Saved", f"Saved: {path}")

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
            self._append_log_line(f"No data for selected date. Placeholder TXT saved to: {output_path}")
        else:
            self._append_log_line(f"Audit complete. Placeholder TXT saved to: {output_path}")
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
        self.audit_date_label.setText(f"Audit Date: {label_value}")
        self.audit_date_label.setStyleSheet(
            f"font-size: 14px; font-weight: 500; color: {self._header_text_color};"
        )

    @Slot()
    def _on_no_data_for_date(self) -> None:
        self._no_data_for_date = True
        self.status_banner.setText("No data for selected date")
        self.status_banner.show()
        self._append_log_line("No data for selected date.")

    def _set_audit_date_pending_label(self) -> None:
        self.audit_date_label.setText("Audit Date: (pending) — Central")
        self.audit_date_label.setStyleSheet(
            f"font-size: 14px; font-weight: 500; color: {self._header_muted_color};"
        )

    def _append_log_line(self, message: str) -> None:
        if not message:
            return
        self.log_panel.appendPlainText(message)
        cursor = self.log_panel.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_panel.setTextCursor(cursor)

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
