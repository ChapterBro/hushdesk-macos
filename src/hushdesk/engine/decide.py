"""Decision helpers for MAR audit vitals and due-cell marks."""

from __future__ import annotations

import logging
from typing import Optional

from hushdesk.pdf.duecell import DueMark


logger = logging.getLogger(__name__)


def rule_triggers(rule_kind: str, threshold: int, vital: Optional[int]) -> bool:
    """Return ``True`` when ``vital`` satisfies the hold rule condition."""

    if vital is None:
        return False

    comparator = rule_kind[-1:]
    if comparator not in {"<", ">"}:
        return False

    value = vital
    if comparator == "<":
        return value < threshold
    if comparator == ">":
        return value > threshold
    return False


def decide_for_dose(rule_kind: str, threshold: int, vital: Optional[int], mark: DueMark) -> str:
    """Return decision label for a single due-cell inspection."""

    if mark == DueMark.DCD:
        return "DCD"

    triggered = rule_triggers(rule_kind, threshold, vital)

    if mark == DueMark.CODE_ALLOWED:
        if triggered:
            return "HELD_OK"
        logger.warning("Allowed code without trigger (ignored)")
        return "NONE"

    if mark in (DueMark.GIVEN_CHECK, DueMark.GIVEN_TIME):
        return "HOLD_MISS" if triggered else "COMPLIANT"

    return "HOLD_MISS" if triggered else "NONE"
