"""Decision engine tests for MAR audit logic."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from hushdesk.engine.decide import decide_for_dose, rule_triggers  # noqa: E402
from hushdesk.pdf.duecell import DueMark  # noqa: E402


class DecisionEngineTests(unittest.TestCase):
    def test_rule_triggers_less_than(self) -> None:
        self.assertTrue(rule_triggers("SBP<", 110, 105))
        self.assertFalse(rule_triggers("SBP<", 110, 120))

    def test_rule_triggers_greater_than(self) -> None:
        self.assertTrue(rule_triggers("HR>", 90, 95))
        self.assertFalse(rule_triggers("HR>", 90, 80))

    def test_decide_dcd_short_circuits(self) -> None:
        result = decide_for_dose("SBP<", 110, 100, DueMark.DCD)
        self.assertEqual(result, "DCD")

    def test_decide_code_allowed_with_trigger(self) -> None:
        result = decide_for_dose("SBP<", 110, 100, DueMark.CODE_ALLOWED)
        self.assertEqual(result, "HELD_OK")

    def test_decide_code_allowed_without_trigger(self) -> None:
        result = decide_for_dose("SBP<", 110, 128, DueMark.CODE_ALLOWED)
        self.assertEqual(result, "NONE")

    def test_decide_given_check_with_trigger(self) -> None:
        result = decide_for_dose("HR<", 60, 55, DueMark.GIVEN_CHECK)
        self.assertEqual(result, "HOLD_MISS")

    def test_decide_given_time_without_trigger(self) -> None:
        result = decide_for_dose("HR<", 60, 78, DueMark.GIVEN_TIME)
        self.assertEqual(result, "COMPLIANT")


if __name__ == "__main__":
    unittest.main()
