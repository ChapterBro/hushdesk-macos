import types

from hushdesk.pdf.rules_normalize import default_rules, evaluate_vitals


def _v(slot, row, sbp=None, hr=None):
    return types.SimpleNamespace(slot_label=slot, slot_row=row, sbp=sbp, hr=hr)


def test_independent_rows_am_pm():
    sbp_rules = [rule for rule in default_rules() if rule.vital == "SBP" and rule.comparator == ">"]
    readings = [_v("AM", 0, sbp=150), _v("PM", 1, sbp=130)]
    decisions = evaluate_vitals(readings, sbp_rules)
    assert any(d["slot_label"] == "AM" and d["sbp"] == 150 for d in decisions)
    assert not any(d["slot_label"] == "PM" and d.get("sbp", 0) > 140 for d in decisions)


def test_hr_and_sbp_independent():
    readings = [_v("AM", 0, sbp=105, hr=58)]
    decisions = evaluate_vitals(readings, default_rules())
    assert any(d["expr"].startswith("SBP<") for d in decisions) or any(
        d["expr"].startswith("HR<") for d in decisions
    )
