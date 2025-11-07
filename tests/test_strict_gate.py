import pytest

from hushdesk.pdf.rules_normalize import parse_rules


@pytest.mark.parametrize(
    "text,strict,why",
    [
        ("Hold for SBP > 160; give if HR > 60", True, "strict sbp>"),
        ("Hold for systolic less than 110", True, "strict sbp<"),
        ("Hold for Pulse greater than 60", True, "strict hr>"),
        ("Hold per RN judgment", False, "reject generic"),
        ("Hold if glucose < 70", False, "reject non-BP"),
        ("Hold for SBP at or equal 160", False, "reject at or/equal"),
        ("Hold for SBP ≤ 160", False, "reject leq"),
        ("Hold for SBP ≥ 160", False, "reject geq"),
    ],
)
def test_strict_gate(text, strict, why):
    r = parse_rules(text)
    assert bool(getattr(r, "strict", False)) == strict, why
