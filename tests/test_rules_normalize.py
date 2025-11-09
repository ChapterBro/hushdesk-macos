"""Tests for strict rule normalization."""

from __future__ import annotations

import unittest

from hushdesk.pdf.rules_normalize import normalize_rule_text


class RuleNormalizeTests(unittest.TestCase):
    def test_dual_thresholds_normalize(self) -> None:
        text = "Hold for SBP greater than 140 and pulse less than 60"
        result = normalize_rule_text(text)
        self.assertTrue(result.strict)
        self.assertEqual(result.sbp_gt, 140)
        self.assertEqual(result.hr_lt, 60)
        self.assertIsNone(result.sbp_lt)
        self.assertIsNone(result.hr_gt)

    def test_symbol_rejection(self) -> None:
        text = "Hold if SBP ≤ 120"
        result = normalize_rule_text(text)
        self.assertFalse(result.strict)
        self.assertIsNone(result.sbp_lt)
        self.assertIsNone(result.sbp_gt)

    def test_symbolic_comparators(self) -> None:
        text = "Hold SBP<100 or HR> 120"
        result = normalize_rule_text(text)
        self.assertTrue(result.strict)
        self.assertEqual(result.sbp_lt, 100)
        self.assertEqual(result.hr_gt, 120)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
