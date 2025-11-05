"""Background worker that simulates auditing a MAR PDF."""

from __future__ import annotations

import logging
import time
from datetime import date
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

try:  # pragma: no cover - optional dependency when tests run without PyMuPDF
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore

from hushdesk.pdf.columns import ColumnBand, select_audit_columns
from hushdesk.pdf.dates import format_mmddyyyy, resolve_audit_date
from hushdesk.placeholders import build_placeholder_output


logger = logging.getLogger(__name__)


class AuditWorker(QObject):
    """Worker that simulates page-by-page progress in a background thread."""

    started = Signal(str)
    progress = Signal(int, int)
    log = Signal(str)
    saved = Signal(str)
    warning = Signal(str)
    audit_date_text = Signal(str)
    summary_counts = Signal(dict)
    no_data_for_date = Signal()
    finished = Signal(Path)

    def __init__(self, input_pdf: Path, delay: float = 0.2) -> None:
        super().__init__()
        self._input_pdf = input_pdf
        self._delay = max(0.05, delay)
        self._audit_date: date | None = None

    @Slot()
    def run(self) -> None:
        self.started.emit(str(self._input_pdf))

        audit_date = resolve_audit_date(self._input_pdf)
        self._audit_date = audit_date
        label_value = f"{format_mmddyyyy(audit_date)} — Central"
        self.audit_date_text.emit(label_value)

        column_bands: list[ColumnBand] = []
        missing_headers: list[int] = []
        doc_pages = 0
        if fitz is None:
            message = "PyMuPDF is not available; skipping column band detection."
            logger.warning(message)
            self.warning.emit(message)
        elif self._input_pdf.exists():
            try:
                with fitz.open(self._input_pdf) as doc:
                    doc_pages = len(doc)
                    self.log.emit(f"Opened doc: pages={doc_pages}")
                    column_bands = select_audit_columns(
                        doc,
                        audit_date,
                        on_page_without_header=missing_headers.append,
                    )
                    self.log.emit(
                        f"Processing {len(column_bands)} band pages (of {doc_pages} total pages)"
                    )
            except Exception as exc:  # pragma: no cover - defensive guard
                message = f"Unable to compute column bands for {self._input_pdf}: {exc}"
                logger.warning(message, exc_info=True)
                self.warning.emit(message)
        else:
            message = f"Input PDF {self._input_pdf} does not exist; skipping column band detection."
            logger.warning(message)
            self.warning.emit(message)

        logger.info("Column selection result for %s: %s", audit_date.isoformat(), column_bands)
        for page_index in missing_headers:
            self.log.emit(f"No header on page {page_index + 1} (skipped)")
        for band in column_bands:
            self.log.emit(
                "ColumnBand page=%d x0=%.1fpt x1=%.1fpt frac=%.3f–%.3f"
                % (band.page_index + 1, band.x0, band.x1, band.frac0, band.frac1)
            )

        output_path = self._input_pdf.with_suffix(".txt")
        reviewed_count = 0

        if not column_bands:
            self.no_data_for_date.emit()
            warning_message = "No data for selected date"
            self.warning.emit(warning_message)
            summary = {
                "reviewed": reviewed_count,
                "hold_miss": 0,
                "held_ok": 0,
                "compliant": 0,
                "dcd": 0,
            }
            self.summary_counts.emit(summary)
            if self._write_placeholder(output_path):
                self.saved.emit(str(output_path))
            self.finished.emit(output_path)
            return

        total_steps = len(column_bands)
        for index, _band in enumerate(column_bands, start=1):
            time.sleep(self._delay)
            self.progress.emit(index, total_steps)
            reviewed_count += 1

        summary = {
            "reviewed": reviewed_count,
            "hold_miss": 0,
            "held_ok": 0,
            "compliant": 0,
            "dcd": 0,
        }
        self.summary_counts.emit(summary)
        if self._write_placeholder(output_path):
            self.saved.emit(str(output_path))

        self.finished.emit(output_path)

    def _write_placeholder(self, output_path: Path) -> bool:
        try:
            output_path.write_text(build_placeholder_output(self._input_pdf))
            return True
        except OSError as exc:
            message = f"Unable to save placeholder TXT to {output_path}: {exc}"
            logger.warning(message)
            self.warning.emit(message)
            # Surface error handling can be added later; for now we still emit finished
            return False
