"""Strict SBP/HR hold rule extraction for medication text blocks."""

from __future__ import annotations

import re
from typing import List

from hushdesk.pdf.rules_normalize import PARSED_RULE_VERSION, Rule, RuleSource, Severity

_GT = r"(?:>|greater\s+than)"
_LT = r"(?:<|less\s+than)"
_NUM = r"(\d{2,3})"
_SBP_LABEL = r"(?:SBP|SYSTOLIC)"
_HR_LABEL = r"(?:HR|PULSE)"

SBP_GT = re.compile(rf"\b{_SBP_LABEL}\b[^\n]{{0,30}}{_GT}[^\d]{{0,5}}{_NUM}", re.IGNORECASE)
SBP_LT = re.compile(rf"\b{_SBP_LABEL}\b[^\n]{{0,30}}{_LT}[^\d]{{0,5}}{_NUM}", re.IGNORECASE)
HR_GT = re.compile(rf"\b{_HR_LABEL}\b[^\n]{{0,30}}{_GT}[^\d]{{0,5}}{_NUM}", re.IGNORECASE)
HR_LT = re.compile(rf"\b{_HR_LABEL}\b[^\n]{{0,30}}{_LT}[^\d]{{0,5}}{_NUM}", re.IGNORECASE)


def parse_strict_rules(text: str, version: str = PARSED_RULE_VERSION) -> List[Rule]:
    """Return strict SBP/HR inequality rules parsed from ``text``."""

    if not text:
        return []

    normalized = " ".join(str(text).split())
    if not normalized:
        return []

    rules: List[Rule] = []
    rules.extend(_matches_to_rules(SBP_GT, normalized, "SBP", ">", version))
    rules.extend(_matches_to_rules(SBP_LT, normalized, "SBP", "<", version))
    rules.extend(_matches_to_rules(HR_GT, normalized, "HR", ">", version))
    rules.extend(_matches_to_rules(HR_LT, normalized, "HR", "<", version))

    seen: set[str] = set()
    unique: List[Rule] = []
    for rule in rules:
        if rule.expr in seen:
            continue
        seen.add(rule.expr)
        unique.append(rule)
    return unique


def _matches_to_rules(pattern: re.Pattern[str], text: str, vital: str, comparator: str, version: str) -> List[Rule]:
    results: List[Rule] = []
    for match in pattern.finditer(text):
        try:
            value = int(match.group(1))
        except (TypeError, ValueError, IndexError):
            continue
        results.append(_make_rule(vital, comparator, value, version))
    return results


def _make_rule(vital: str, comparator: str, threshold: int, version: str) -> Rule:
    suffix = "gt" if comparator == ">" else "lt"
    return Rule(
        id=f"{vital.lower()}_{suffix}_{threshold}",
        expr=f"{vital}{comparator}{threshold}",
        severity=Severity.WARN,
        source=RuleSource.PARSED,
        version=version,
        vital=vital,
        comparator=comparator,
        threshold=threshold,
    )


__all__ = ["parse_strict_rules"]
