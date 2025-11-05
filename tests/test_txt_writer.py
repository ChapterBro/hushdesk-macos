"""TXT writer tests."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hushdesk.report.model import DecisionRecord
from hushdesk.report.txt_writer import write_report


class TxtWriterTests(unittest.TestCase):
    def test_write_report_formats_sections(self) -> None:
        records = [
            DecisionRecord(
                hall="Bridgeman",
                date_mmddyyyy="11/03/2025",
                source_basename="sample.pdf",
                room_bed="307-1",
                dose="AM",
                kind="HOLD-MISS",
                rule_text="Hold if SBP < 110",
                vital_text="BP 101/44",
                code=None,
                dcd_reason=None,
                notes="split",
            ),
            DecisionRecord(
                hall="Bridgeman",
                date_mmddyyyy="11/03/2025",
                source_basename="sample.pdf",
                room_bed="307-1",
                dose="PM",
                kind="HELD-OK",
                rule_text="Hold if HR < 60",
                vital_text="HR 58",
                code=12,
                dcd_reason=None,
                notes=None,
            ),
            DecisionRecord(
                hall="Bridgeman",
                date_mmddyyyy="11/03/2025",
                source_basename="sample.pdf",
                room_bed="305-1",
                dose="AM",
                kind="COMPLIANT",
                rule_text="Hold if SBP < 90",
                vital_text="BP 120/70",
                code=None,
                dcd_reason=None,
                notes=None,
            ),
            DecisionRecord(
                hall="Bridgeman",
                date_mmddyyyy="11/03/2025",
                source_basename="sample.pdf",
                room_bed="309-1",
                dose="PM",
                kind="DC'D",
                rule_text="Hold if SBP < 100",
                vital_text="BP missing",
                code=None,
                dcd_reason="X in due cell",
                notes=None,
            ),
        ]
        counts = {"reviewed": 4, "hold_miss": 1, "held_ok": 1, "compliant": 1, "dcd": 1}
        notes = ["Room not resolved for block on page 3"]

        with TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "report.txt"
            write_report(records, counts, "11/03/2025", "Bridgeman", "sample.pdf", out_path, notes)
            content = out_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(content[0], "11/03/2025 · Hall: BRIDGEMAN · Source: sample.pdf")
        self.assertEqual(
            content[1],
            "Reviewed: 4 · Hold-Miss: 1 · Held-OK: 1 · Compliant: 1 · DC'D: 1",
        )
        self.assertIn("Exceptions —", content)
        self.assertTrue(
            any(
                "HOLD-MISS — 307-1 (AM (split)) — Hold if SBP < 110; BP 101/44" in line
                for line in content
            )
        )
        self.assertTrue(
            any(
                line.startswith("HELD-OK — 307-1 (PM)") and "| code 12" in line for line in content
            )
        )
        self.assertIn("All Reviewed —", content)
        self.assertTrue(any(line.startswith("Notes — Room not resolved") for line in content))
        self.assertTrue(content[-1].startswith("Generated: "))


if __name__ == "__main__":
    unittest.main()
