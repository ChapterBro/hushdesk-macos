"""Tests for filename-first audit date resolution and worker integration."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from hushdesk.pdf.dates import format_mmddyyyy, resolve_audit_date  # noqa: E402
from hushdesk.workers.audit_worker import AuditWorker  # noqa: E402


class DateParsingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_filename_previous_day(self) -> None:
        path = Path("Administration Record Report 2025-11-04.pdf")
        audit_date = resolve_audit_date(path)
        self.assertEqual(format_mmddyyyy(audit_date), "11/03/2025")

    def test_filename_wins_over_printed_stub(self) -> None:
        # The filename is authoritative until printed-on parsing is implemented.
        path = Path("MAR Report 2025-11-04 printed 2025-11-06.pdf")
        audit_date = resolve_audit_date(path)
        self.assertEqual(format_mmddyyyy(audit_date), "11/03/2025")


class AuditWorkerSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_worker_emits_audit_label_and_no_data_banner(self) -> None:
        with TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "Administration Record Report 2025-11-04.pdf"
            worker = AuditWorker(input_pdf=pdf_path, delay=0.05)

            emitted_labels: List[str] = []
            banner_hits: List[bool] = []

            worker.audit_date_text.connect(emitted_labels.append)
            worker.no_data_for_date.connect(lambda: banner_hits.append(True))

            with patch("hushdesk.workers.audit_worker.time.sleep", return_value=None), patch(
                "hushdesk.workers.audit_worker.logger.info"
            ) as mock_logger:
                worker.run()

            self.assertIn("11/03/2025 — Central", emitted_labels)
            self.assertTrue(banner_hits, "Expected no-data banner signal emission.")
            self.assertTrue(
                any("Column selection result" in call.args[0] for call in mock_logger.call_args_list),
                "Expected column clamp log entry.",
            )

            output_path = pdf_path.with_suffix(".txt")
            self.assertTrue(output_path.exists(), "Placeholder TXT should be created.")


if __name__ == "__main__":
    unittest.main()
