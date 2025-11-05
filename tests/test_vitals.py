"""Tests for vital sign parsing utilities."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from hushdesk.pdf.vitals import parse_bp_token, parse_hr_token  # noqa: E402


class VitalParsingTests(unittest.TestCase):
    def test_parse_bp_token_with_newline(self) -> None:
        text = "120/\n80"
        self.assertEqual(parse_bp_token(text), "120/80")

    def test_parse_bp_token_invalid(self) -> None:
        self.assertIsNone(parse_bp_token("No BP documented"))

    def test_parse_hr_token_with_label(self) -> None:
        self.assertEqual(parse_hr_token("Pulse 78"), 78)

    def test_parse_hr_token_plain_number(self) -> None:
        self.assertEqual(parse_hr_token("64"), 64)

    def test_parse_hr_token_invalid(self) -> None:
        self.assertIsNone(parse_hr_token("N/A"))


if __name__ == "__main__":
    unittest.main()
