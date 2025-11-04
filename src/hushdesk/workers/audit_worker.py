"""Background worker that simulates auditing a MAR PDF."""

from __future__ import annotations

import logging
import time
from datetime import date
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from hushdesk.pdf.columns import select_audit_column
from hushdesk.pdf.dates import format_mmddyyyy, resolve_audit_date
from hushdesk.placeholders import build_placeholder_output


logger = logging.getLogger(__name__)


class AuditWorker(QObject):
    """Worker that simulates page-by-page progress in a background thread."""

    progress_changed = Signal(int, int)
    audit_date_resolved = Signal(str)
    no_data_for_date = Signal()
    finished = Signal(Path)

    def __init__(self, input_pdf: Path, total_pages: int = 10, delay: float = 0.2) -> None:
        super().__init__()
        self._input_pdf = input_pdf
        self._total_pages = max(1, total_pages)
        self._delay = max(0.05, delay)
        self._audit_date: date | None = None

    @Slot()
    def run(self) -> None:
        audit_date = resolve_audit_date(self._input_pdf)
        self._audit_date = audit_date
        label_value = f"{format_mmddyyyy(audit_date)} — Central"
        self.audit_date_resolved.emit(label_value)

        column_bounds = select_audit_column(audit_date)
        logger.info("Column selection result for %s: %s", audit_date.isoformat(), column_bounds)
        output_path = self._input_pdf.with_suffix(".txt")

        if column_bounds is None:
            self.no_data_for_date.emit()
            self._write_placeholder(output_path)
            self.finished.emit(output_path)
            return

        for page in range(1, self._total_pages + 1):
            time.sleep(self._delay)
            self.progress_changed.emit(page, self._total_pages)

        self._write_placeholder(output_path)

        self.finished.emit(output_path)

    def _write_placeholder(self, output_path: Path) -> None:
        try:
            output_path.write_text(build_placeholder_output(self._input_pdf))
        except OSError:
            # Surface error handling can be added later; for now we still emit finished
            pass
