from hushdesk.pdf.rules_master import parse_strict_rules


def test_parse_sbp_gt_lt():
    rules = parse_strict_rules("HOLD FOR SBP GREATER THAN 140 and hold for SBP < 110")
    exprs = sorted(rule.expr for rule in rules)
    assert "SBP>140" in exprs
    assert "SBP<110" in exprs


def test_parse_hr_pulse():
    rules = parse_strict_rules("Hold for pulse less than 60; HR > 110")
    exprs = sorted(rule.expr for rule in rules)
    assert "HR<60" in exprs
    assert "HR>110" in exprs
