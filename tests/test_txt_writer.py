"""TXT writer tests."""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hushdesk.report.model import DecisionRecord
from hushdesk.report.txt_writer import write_report


class TxtWriterTests(unittest.TestCase):
    def test_write_report_respects_sectioning_and_order(self) -> None:
        records = [
            DecisionRecord(
                hall="Bridgeman",
                date_mmddyyyy="11/03/2025",
                source_basename="sample.pdf",
                room_bed="307-1",
                dose="AM",
                kind="HOLD-MISS",
                rule_text="Hold if SBP < 110 | Source: Policy 2025",
                vital_text="BP 101/44",
                code=None,
                dcd_reason=None,
                notes="split",
                extras={"state_detail": "given 0800"},
            ),
            DecisionRecord(
                hall="Bridgeman",
                date_mmddyyyy="11/03/2025",
                source_basename="sample.pdf",
                room_bed="307-1",
                dose="PM",
                kind="HELD-APPROPRIATE",
                rule_text="Hold if HR < 60",
                vital_text="HR 58",
                code=12,
                dcd_reason=None,
                notes=None,
                extras={"state_detail": "code 12"},
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
                extras={"state_detail": "given 0800"},
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
                extras={"state_detail": "dc'd"},
            ),
            DecisionRecord(
                hall="Bridgeman",
                date_mmddyyyy="11/03/2025",
                source_basename="sample.pdf",
                room_bed="305-2",
                dose="PM",
                kind="HOLD-MISS",
                rule_text="Hold if HR < 58",
                vital_text="HR 57",
                code=None,
                dcd_reason=None,
                notes=None,
                extras={"state_detail": "given PM"},
            ),
        ]
        counts = {"reviewed": 5, "hold_miss": 2, "held_appropriate": 1, "compliant": 1, "dcd": 1}
        notes = [
            "Vitals missing (unexpected) — 309-1 (AM)",
            "Vitals missing (unexpected) — 309-1 (AM (split))",
            "Room not resolved for block on page 3",
        ]

        with TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "report.txt"
            final_path = write_report(
                records,
                counts,
                "11/03/2025",
                "Bridgeman",
                "sample.pdf",
                out_path,
                notes,
            )
            content = final_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(content[0], "Date: 11-03-2025")
        self.assertEqual(content[1], "Hall: BRIDGEMAN")
        self.assertEqual(content[2], "Source: sample.pdf")
        self.assertEqual(
            content[4],
            "Counts (chips): Reviewed 5 · Hold-Miss 2 · Held-Appropriate 1 · Compliant 1 · DC'D 1",
        )

        exceptions_idx = content.index("Exceptions —")
        all_reviewed_idx = content.index("All Reviewed —")

        exceptions_lines = [
            line
            for line in content[exceptions_idx + 1 : all_reviewed_idx]
            if line.strip()
        ]

        pattern = re.compile(r"^(?P<kind>[^—]+) — (?P<room>[^()]+?) \((?P<dose>[^)]+)\)")
        exception_keys = [pattern.match(line).groups() for line in exceptions_lines]
        self.assertEqual(
            exception_keys,
            [
                ("HOLD-MISS", "305-2", "PM"),
                ("HOLD-MISS", "307-1", "AM"),
                ("HELD-APPROPRIATE", "307-1", "PM"),
            ],
        )

        all_notes_start = next((i for i, line in enumerate(content) if line.startswith("Notes —")), len(content))
        reviewed_lines = [
            line
            for line in content[all_reviewed_idx + 1 : all_notes_start]
            if line.strip()
        ]
        reviewed_keys = [pattern.match(line).groups() for line in reviewed_lines]
        self.assertEqual(
            reviewed_keys,
            [
                ("HOLD-MISS", "305-2", "PM"),
                ("HOLD-MISS", "307-1", "AM"),
                ("HELD-APPROPRIATE", "307-1", "PM"),
                ("COMPLIANT", "305-1", "AM"),
                ("DC'D", "309-1", "PM"),
            ],
        )

        self.assertTrue(
            any("Hold if SBP < 110" in line and "Source" not in line for line in reviewed_lines)
        )
        self.assertTrue(
            any("Hold if HR < 60; HR 58; code 12" in line for line in reviewed_lines)
        )

        note_lines = [line for line in content if line.startswith("Notes —")]
        self.assertEqual(len(note_lines), 3)
        self.assertIn("Notes — AM/PM labels missing (split)", note_lines)
        self.assertTrue(any(line.startswith("Notes — Room not resolved") for line in note_lines))
        self.assertTrue(any(line.startswith("Notes — Vitals missing") for line in note_lines))

        self.assertTrue(content[-1].startswith("Generated: "))


if __name__ == "__main__":
    unittest.main()
