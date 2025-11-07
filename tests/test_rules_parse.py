"""Strict rule parsing tests."""

from __future__ import annotations

import unittest

from hushdesk.engine.rules import parse_rule_text


class RuleParsingTests(unittest.TestCase):
    def test_symbol_forms_detected(self) -> None:
        text = "Hold if SBP < 110 and HR < 60"
        specs = parse_rule_text(text)
        self.assertEqual(len(specs), 2)
        kinds = {spec.kind for spec in specs}
        self.assertIn("SBP<", kinds)
        self.assertIn("HR<", kinds)

    def test_word_forms_detected(self) -> None:
        text = "Hold for systolic greater than 160"
        specs = parse_rule_text(text)
        self.assertEqual(len(specs), 1)
        spec = specs[0]
        self.assertEqual(spec.kind, "SBP>")
        self.assertEqual(spec.threshold, 160)
        self.assertEqual(spec.description, "Hold if SBP > 160")

    def test_rejects_fuzzy_tokens(self) -> None:
        text = "Hold if SBP ≤ 110 or HR ≥ 60"
        specs = parse_rule_text(text)
        self.assertEqual(specs, [])

    def test_and_or_dual_rules(self) -> None:
        text = "Hold if SBP < 100 and/or HR < 60"
        specs = parse_rule_text(text)
        self.assertEqual(len(specs), 2)
        self.assertEqual(specs[0].kind, "SBP<")
        self.assertEqual(specs[0].threshold, 100)
        self.assertEqual(specs[1].kind, "HR<")
        self.assertEqual(specs[1].threshold, 60)


if __name__ == "__main__":
    unittest.main()
