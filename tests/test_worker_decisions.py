"""Audit worker decision tests using synthetic fixtures."""

from __future__ import annotations

import unittest
from collections import Counter
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hushdesk import accel
from hushdesk.engine.rules import RuleSpec
from hushdesk.pdf.duecell import DueMark
from hushdesk.pdf.mar_grid_extract import DueRecord, PageExtraction
from hushdesk.pdf.mar_parser_mupdf import run_mar_audit
from hushdesk.pdf.rules_normalize import RuleSet
from hushdesk.workers.audit_worker import AuditWorker
from .fixtures.synth import (
    ALLOWED_CODE_RULE_TEXT,
    BASE_BLOCK_BBOX,
    BASE_COLUMN_BAND,
    BASE_ROOM_INFO,
    DummyPage,
    HR_RULE_TEXT,
    build_row_bands,
)

SAMPLE_SOURCE = "Administration Record Report 2025-11-04.pdf"
SAMPLE_DATE = "11/03/2025"


class AuditWorkerDecisionTests(unittest.TestCase):
    def _evaluate_case(
        self,
        rule_text: str,
        mark: DueMark,
        mark_text: str,
        vitals_side_effect: list[dict],
        row_bands=None,
    ):
        worker = AuditWorker(Path(SAMPLE_SOURCE))
        records = []
        hall_counts = Counter()
        record_payloads: list[dict] = []
        anomalies: list[dict] = []
        run_notes: list[str] = []
        notes_seen: set[str] = set()
        row_bands = row_bands or build_row_bands()

        with patch.object(
            AuditWorker,
            "_find_block_candidates",
            return_value=[(BASE_BLOCK_BBOX, rule_text)],
        ), patch(
            "hushdesk.workers.audit_worker.find_row_bands_for_block",
            return_value=row_bands,
        ), patch(
            "hushdesk.workers.audit_worker.extract_vitals_in_band",
            side_effect=vitals_side_effect,
        ) as vitals_mock, patch(
            "hushdesk.workers.audit_worker.detect_due_mark",
            return_value=mark,
        ), patch.object(
            AuditWorker,
            "_collect_text",
            return_value=mark_text,
        ), patch.object(
            AuditWorker,
            "_resolve_room_info",
            return_value=(BASE_ROOM_INFO, [{"text": BASE_ROOM_INFO[0]}]),
        ), patch.object(
            AuditWorker,
            "_page_render_metrics",
            return_value=(1.0, 100.0, 100.0),
        ):
            counts = worker._evaluate_column_band(
                DummyPage(),
                BASE_COLUMN_BAND,
                SAMPLE_DATE,
                SAMPLE_SOURCE,
                records,
                record_payloads,
                anomalies,
                hall_counts,
                run_notes,
                notes_seen,
            )

        return counts, records, vitals_mock.call_count

    def test_code_allowed_with_trigger_yields_held_appropriate(self) -> None:
        vitals = [
            {"bp": "101/44", "hr": None},  # bp band
            {"bp": None, "hr": None},  # hr band
            {"bp": None, "hr": None},  # slot AM
        ]
        counts, records, calls = self._evaluate_case(
            ALLOWED_CODE_RULE_TEXT,
            DueMark.CODE_ALLOWED,
            "code 15",
            vitals,
            row_bands=build_row_bands(pm=None),
        )

        self.assertEqual(calls, 3)
        self.assertEqual(counts["reviewed"], 1)
        self.assertEqual(counts["held_appropriate"], 1)
        self.assertEqual(len(records), 1)

        record = records[0]
        self.assertEqual(record.room_bed, BASE_ROOM_INFO[0])
        self.assertEqual(record.dose, "AM")
        self.assertEqual(record.kind, "HELD-APPROPRIATE")
        self.assertEqual(record.code, 15)
        self.assertEqual(record.vital_text, "BP 101/44")

    def test_given_time_trigger_yields_hold_miss(self) -> None:
        row_bands = build_row_bands(bp=None, hr=(320.0, 340.0), am=(340.0, 360.0), pm=None)
        vitals = [
            {"bp": None, "hr": 58},  # hr band
            {"bp": None, "hr": 58},  # slot
        ]
        counts, records, calls = self._evaluate_case(
            HR_RULE_TEXT,
            DueMark.GIVEN_TIME,
            "07:30",
            vitals,
            row_bands=row_bands,
        )

        self.assertEqual(calls, 2)
        self.assertEqual(counts["reviewed"], 1)
        self.assertEqual(counts["hold_miss"], 1)
        self.assertEqual(len(records), 1)

        record = records[0]
        self.assertEqual(record.kind, "HOLD-MISS")
        self.assertEqual(record.vital_text, "HR 58")
        self.assertIsNone(record.code)

    def test_dcd_mark_yields_dcd_record(self) -> None:
        vitals = [
            {"bp": None, "hr": None},  # slot fetch
        ]
        counts, records, calls = self._evaluate_case(
            ALLOWED_CODE_RULE_TEXT,
            DueMark.DCD,
            "X",
            vitals,
            row_bands=build_row_bands(bp=None, hr=None, am=(340.0, 360.0), pm=None),
        )

        self.assertEqual(calls, 1)
        self.assertEqual(counts["dcd"], 1)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.kind, "DC'D")
        self.assertEqual(record.dcd_reason, "X in due cell")

    def test_given_without_trigger_yields_compliant(self) -> None:
        vitals = [
            {"bp": "128/74", "hr": None},  # bp band
            {"bp": None, "hr": None},  # hr band
            {"bp": None, "hr": None},  # slot AM
        ]
        counts, records, calls = self._evaluate_case(
            ALLOWED_CODE_RULE_TEXT,
            DueMark.GIVEN_CHECK,
            "√",
            vitals,
            row_bands=build_row_bands(pm=None),
        )

        self.assertEqual(calls, 3)
        self.assertEqual(counts["compliant"], 1)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.kind, "COMPLIANT")
        self.assertEqual(record.vital_text, "BP 128/74")

    def test_dual_rules_emit_two_decisions(self) -> None:
        vitals = [
            {"bp": "128/74", "hr": None},  # bp band
            {"bp": None, "hr": 58},  # hr band
            {"bp": None, "hr": 58},  # slot AM
        ]
        counts, records, calls = self._evaluate_case(
            "Hold if SBP < 110 and HR < 60",
            DueMark.GIVEN_TIME,
            "07:30",
            vitals,
            row_bands=build_row_bands(pm=None),
        )

        self.assertEqual(calls, 3)
        self.assertEqual(counts["reviewed"], 1)
        self.assertEqual(counts["compliant"], 1)
        self.assertEqual(counts["hold_miss"], 1)

    def test_reviewed_equals_chip_sum_instrumentation(self) -> None:
        bbox = (0.0, 0.0, 1.0, 1.0)
        given_rules = RuleSet()
        given_rules.strict = True
        given_rules.hr_lt = 60
        allowed_rules = RuleSet()
        allowed_rules.strict = True
        allowed_rules.sbp_lt = 110
        empty_rules = RuleSet()
        empty_rules.strict = True
        empty_rules.hr_lt = 55

        due_given = DueRecord(
            hall="BRIDGEMAN",
            room="301-1",
            page_index=0,
            time_slot="AM",
            normalized_slot="am",
            sbp=None,
            hr=70,
            bp_text="",
            hr_text="70",
            due_text="√",
            state="GIVEN",
            code=None,
            rules=given_rules,
            parametered=True,
            rule_text="Hold if HR < 60",
            bp_bbox=None,
            hr_bbox=None,
            due_bbox=bbox,
            audit_band=bbox,
            track_band=(0.0, 1.0),
            mark_category="given",
        )

        due_allowed = DueRecord(
            hall="BRIDGEMAN",
            room="301-1",
            page_index=0,
            time_slot="AM",
            normalized_slot="am",
            sbp=95,
            hr=None,
            bp_text="95/60",
            hr_text="",
            due_text="11",
            state="CODE",
            code=11,
            rules=allowed_rules,
            parametered=True,
            rule_text="Hold if SBP < 110",
            bp_bbox=None,
            hr_bbox=None,
            due_bbox=bbox,
            audit_band=bbox,
            track_band=(0.0, 1.0),
            mark_category="allowed_code",
        )

        due_empty = DueRecord(
            hall="BRIDGEMAN",
            room="301-1",
            page_index=0,
            time_slot="AM",
            normalized_slot="am",
            sbp=None,
            hr=None,
            bp_text="",
            hr_text="",
            due_text="",
            state="EMPTY",
            code=None,
            rules=empty_rules,
            parametered=True,
            rule_text="Hold if HR < 55",
            bp_bbox=None,
            hr_bbox=None,
            due_bbox=bbox,
            audit_band=bbox,
            track_band=(0.0, 1.0),
            mark_category="empty",
        )

        page_stub = SimpleNamespace(page_index=0, pixmap=None)
        extraction = PageExtraction(
            page=page_stub,
            blocks=[],
            records=[due_given, due_allowed, due_empty],
            highlights=None,
        )

        with patch(
            "hushdesk.pdf.mar_parser_mupdf.iter_canon_pages",
            return_value=[SimpleNamespace()],
        ), patch(
            "hushdesk.pdf.mar_parser_mupdf.extract_pages",
            return_value=[extraction],
        ), patch(
            "hushdesk.pdf.mar_parser_mupdf.draw_med_blocks_debug",
            return_value=Path("debug/mock.png"),
        ):
            result = run_mar_audit(
                "fake.pdf",
                "BRIDGEMAN",
                date(2025, 11, 5),
            )

        counts = result.counts
        expected_reviewed = (
            counts["hold_miss"]
            + counts["held_appropriate"]
            + counts["compliant"]
            + counts["dcd"]
        )
        self.assertEqual(counts["reviewed"], expected_reviewed)
        self.assertEqual(counts["held_appropriate"], 1)
        self.assertEqual(counts["compliant"], 1)
        self.assertEqual(counts["dcd"], 0)

        instrumentation = result.instrumentation
        self.assertEqual(instrumentation["parametered_total"], 3)
        self.assertEqual(instrumentation["parametered"], 3)
        self.assertEqual(instrumentation["nonchip"], 1)
        breakdown = instrumentation.get("nonchip_breakdown")
        self.assertIsInstance(breakdown, dict)
        self.assertEqual(breakdown.get("empty"), 1)
        self.assertEqual(breakdown.get("other_code"), 0)
        self.assertEqual(instrumentation["other_code"], 0)
        self.assertEqual(instrumentation["empty"], 1)
        self.assertEqual(
            instrumentation["parametered_total"] - counts["reviewed"],
            instrumentation["nonchip_record_delta"],
        )
        records = result.records
        chip_kinds = [record.kind for record in records if record.chip]
        self.assertCountEqual(chip_kinds, ["COMPLIANT", "HELD-APPROPRIATE"])
        self.assertTrue(
            any(not record.chip and record.kind == "COMPLIANT" for record in records)
        )

    @unittest.skipUnless(accel.ACCEL_AVAILABLE, "Rust accelerator not available")
    def test_rust_toggle_preserves_results(self) -> None:
        vitals = [
            {"bp": "128/74", "hr": None},
            {"bp": None, "hr": None},
            {"bp": None, "hr": None},
        ]
        baseline_counts, baseline_records, _ = self._evaluate_case(
            ALLOWED_CODE_RULE_TEXT,
            DueMark.GIVEN_CHECK,
            "√",
            vitals,
            row_bands=build_row_bands(pm=None),
        )

        with patch.object(accel, "USE_RUST", True):
            rust_counts, rust_records, _ = self._evaluate_case(
                ALLOWED_CODE_RULE_TEXT,
                DueMark.GIVEN_CHECK,
                "√",
                vitals,
                row_bands=build_row_bands(pm=None),
            )

        self.assertEqual(rust_counts, baseline_counts)
        baseline_summary = [(record.kind, record.vital_text, record.code) for record in baseline_records]
        rust_summary = [(record.kind, record.vital_text, record.code) for record in rust_records]
        self.assertEqual(rust_summary, baseline_summary)

    def test_format_decision_log_for_allowed_code(self) -> None:
        worker = AuditWorker(Path(SAMPLE_SOURCE))
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
            "HELD-APPROPRIATE — 101-1 (AM) — Hold if SBP < 110; BP 101/44; code 15",
        )

    def test_format_decision_log_for_dcd(self) -> None:
        worker = AuditWorker(Path(SAMPLE_SOURCE))
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
