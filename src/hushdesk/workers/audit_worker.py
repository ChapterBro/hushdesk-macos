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

        column_bands: list[ColumnBand] = []
        if fitz is None:
            logger.warning("PyMuPDF is not available; skipping column band detection.")
        elif self._input_pdf.exists():
            try:
                with fitz.open(self._input_pdf) as doc:
                    column_bands = select_audit_columns(doc, audit_date)
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.warning(
                    "Unable to compute column bands for %s: %s",
                    self._input_pdf,
                    exc,
                    exc_info=True,
                )
        else:
            logger.warning(
                "Input PDF %s does not exist; skipping column band detection.", self._input_pdf
            )

        logger.info("Column selection result for %s: %s", audit_date.isoformat(), column_bands)
        output_path = self._input_pdf.with_suffix(".txt")

        if not column_bands:
            self.no_data_for_date.emit()
            self._write_placeholder(output_path)
            self.finished.emit(output_path)
            return

        for band in column_bands:
            logger.info(
                "Page %d band: x0=%.2fpt x1=%.2fpt width=%.2fpt height=%.2fpt frac=[%.4f, %.4f]",
                band.page_index + 1,
                band.x0,
                band.x1,
                band.page_width,
                band.page_height,
                band.frac0,
                band.frac1,
            )

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
