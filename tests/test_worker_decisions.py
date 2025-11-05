"""Audit worker decision smoke tests."""

from __future__ import annotations

import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication

from hushdesk.engine.rules import RuleSpec
from hushdesk.pdf.columns import ColumnBand
from hushdesk.pdf.duecell import DueMark
from hushdesk.pdf.rows import RowBands
from hushdesk.workers.audit_worker import AuditWorker


class DummyPage:
    def get_text(self, kind: str) -> dict:  # noqa: D401
        return {}


class AuditWorkerDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QCoreApplication.instance() or QCoreApplication([])

    def test_code_allowed_with_trigger_yields_held_ok(self) -> None:
        worker = AuditWorker(Path("Administration Record Report 2025-11-04.pdf"))

        band = ColumnBand(
            page_index=0,
            x0=120.0,
            x1=220.0,
            page_width=420.0,
            page_height=640.0,
            frac0=0.25,
            frac1=0.40,
        )

        block_bbox = (80.0, 280.0, 260.0, 360.0)
        rule_text = "Hold if SBP < 110"

        mock_vitals_returns = [
            {"bp": "101/44", "hr": None},
            {"bp": None, "hr": None},
        ]

        records = []
        hall_counts = Counter()
        run_notes: list[str] = []
        notes_seen: set[str] = set()

        with patch.object(
            AuditWorker,
            "_find_block_candidates",
            return_value=[(block_bbox, rule_text)],
        ), patch(
            "hushdesk.workers.audit_worker.find_row_bands_for_block",
            return_value=RowBands(bp=(300.0, 320.0)),
        ), patch(
            "hushdesk.workers.audit_worker.extract_vitals_in_band",
            side_effect=mock_vitals_returns,
        ) as vitals_mock, patch(
            "hushdesk.workers.audit_worker.detect_due_mark",
            return_value=DueMark.CODE_ALLOWED,
        ), patch.object(
            AuditWorker,
            "_collect_text",
            return_value="code 15",
        ), patch.object(
            AuditWorker,
            "_resolve_room_info",
            return_value=(("101-1", "Mercer"), [{"text": "101-1"}]),
        ):
            counts = worker._evaluate_column_band(
                DummyPage(),
                band,
                "11/03/2025",
                "Administration Record Report 2025-11-04.pdf",
                records,
                hall_counts,
                run_notes,
                notes_seen,
            )

        self.assertEqual(vitals_mock.call_count, 2)
        self.assertEqual(counts["reviewed"], 1)
        self.assertEqual(counts["held_ok"], 1)
        self.assertEqual(counts["hold_miss"], 0)
        self.assertEqual(counts["compliant"], 0)
        self.assertEqual(counts["dcd"], 0)
        self.assertEqual(len(records), 1)
        decision = records[0]
        self.assertEqual(decision.kind, "HELD-OK")
        self.assertEqual(decision.room_bed, "101-1")
        self.assertEqual(decision.dose, "AM")
        self.assertEqual(decision.code, 15)

    def test_format_decision_log_for_allowed_code(self) -> None:
        worker = AuditWorker(Path("Administration Record Report 2025-11-04.pdf"))
        rule = RuleSpec(kind="SBP<", threshold=110, description="Hold if SBP < 110")
        message = worker._format_decision_log(
            decision="HELD_OK",
            room_bed="101-1",
            slot_label="AM",
            rule=rule,
            bp_value="101/44",
            hr_value=None,
            mark=DueMark.CODE_ALLOWED,
            mark_text="code 15",
        )
        self.assertEqual(
            message,
            "HELD-OK — 101-1 (AM) — Hold if SBP < 110; BP 101/44 | code 15",
        )

    def test_format_decision_log_for_dcd(self) -> None:
        worker = AuditWorker(Path("Administration Record Report 2025-11-04.pdf"))
        rule = RuleSpec(kind="SBP<", threshold=110, description="Hold if SBP < 110")
        message = worker._format_decision_log(
            decision="DCD",
            room_bed="101-1",
            slot_label="PM",
            rule=rule,
            bp_value=None,
            hr_value=None,
            mark=DueMark.DCD,
            mark_text="X",
        )
        self.assertEqual(
            message,
            "DC'D — 101-1 (PM) — X in due cell",
        )


if __name__ == "__main__":
    unittest.main()
