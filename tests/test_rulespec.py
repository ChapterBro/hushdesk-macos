"""Tests for the RuleSpec helper used during rule parsing."""

from hushdesk.workers.audit_worker import RuleSpec


def test_rulespec_construction_with_kind() -> None:
    spec = RuleSpec(kind="SBP<", threshold=110, description="Hold if SBP < 110")
    assert spec.kind == "SBP<"
    assert spec.threshold == 110
    assert spec.description == "Hold if SBP < 110"


def test_rulespec_construction_via_from_kwargs() -> None:
    spec = RuleSpec.from_kwargs(rule_kind="HR>", threshold=60, description="Hold if HR > 60")
    assert spec.kind == "HR>"
    assert spec.threshold == 60
    assert spec.description == "Hold if HR > 60"
