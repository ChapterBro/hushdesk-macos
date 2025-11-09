"""
Safe placeholder for MAR rule normalization logic.

This module exists solely to unblock the tracer pipeline while the canonical
implementations live in another branch.  It parses simple SBP / HR rule clauses
from block text so that downstream code can keep emitting RuleSet metadata
without crashing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
from typing import List, Optional

logger = logging.getLogger(__name__)

_CLAUSE_RE = re.compile(
    r"(?i)\b(?P<vital>SBP|HR)\s*(?P<comparator>>=|<=|>|<)\s*(?P<threshold>\d{2,3})"
)


@dataclass(slots=True)
class RuleClause:
    """Minimal comparator/threshold pair used for placeholder rules."""

    vital: str
    comparator: str
    threshold: int

    def as_dict(self) -> dict[str, object]:
        return {
            "vital": self.vital,
            "comparator": self.comparator,
            "threshold": self.threshold,
        }


@dataclass(slots=True)
class RuleSet:
    """No-op rule container compatible with the MAR parser expectations."""

    text: str = ""
    strict: bool = False
    sbp_lt: Optional[int] = None
    sbp_gt: Optional[int] = None
    hr_lt: Optional[int] = None
    hr_gt: Optional[int] = None
    clauses: List[RuleClause] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "strict": self.strict,
            "sbp_lt": self.sbp_lt,
            "sbp_gt": self.sbp_gt,
            "hr_lt": self.hr_lt,
            "hr_gt": self.hr_gt,
            "clauses": [clause.as_dict() for clause in self.clauses],
        }


def _apply_clause(rule_set: RuleSet, clause: RuleClause) -> None:
    vital = clause.vital.upper()
    comparator = clause.comparator
    threshold = clause.threshold
    if vital == "SBP":
        if comparator in ("<", "<="):
            rule_set.sbp_lt = threshold
        elif comparator in (">", ">="):
            rule_set.sbp_gt = threshold
    elif vital == "HR":
        if comparator in ("<", "<="):
            rule_set.hr_lt = threshold
        elif comparator in (">", ">="):
            rule_set.hr_gt = threshold
    rule_set.clauses.append(clause)
    rule_set.strict = True


def parse_rules(text: str | None) -> RuleSet:
    """
    Parse a medication block text blob into a lightweight RuleSet.

    The placeholder implementation only understands simple ``SBP < 90`` or
    ``HR > 120`` style clauses. Anything else preserves the raw text while
    keeping the RuleSet usable by the MAR parser.
    """

    blob = (text or "").strip()
    rule_set = RuleSet(text=blob)
    if not blob:
        return rule_set

    matches = list(_CLAUSE_RE.finditer(blob))
    if not matches:
        logger.debug("rules_normalize stub: no explicit clauses detected")
        return rule_set

    for match in matches:
        vital = match.group("vital").upper()
        comparator = match.group("comparator")
        threshold = int(match.group("threshold"))
        _apply_clause(rule_set, RuleClause(vital=vital, comparator=comparator, threshold=threshold))
    return rule_set


__all__ = ["RuleSet", "RuleClause", "parse_rules"]
