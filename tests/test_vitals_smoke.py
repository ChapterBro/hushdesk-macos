"""Lightweight vitals + rule sanity checks for the canonical parser."""

from __future__ import annotations

from hushdesk.pdf.mar_tokens import bp_values, pulse_value
from hushdesk.pdf.mupdf_canon import CanonWord
from hushdesk.pdf.rules_normalize import RuleSet, default_rules


def _word(text: str) -> CanonWord:
    return CanonWord(text=text, bbox=(0.0, 0.0, 1.0, 1.0), center=(0.5, 0.5))


def test_bp_and_pulse_detection() -> None:
    words = [_word("BP"), _word("142/86"), _word("MMHG")]
    assert bp_values(words) == 142

    pulse_words = [_word("Pulse"), _word("58"), _word("bpm")]
    assert pulse_value(pulse_words) == 58


def test_default_ruleset_thresholds() -> None:
    rules = default_rules()
    assert isinstance(rules, RuleSet)
    assert rules.strict is True
    assert rules.sbp_gt == 140
    assert rules.hr_lt == 60
    assert rules.hr_gt == 110
