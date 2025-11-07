"""Strict rule parsing helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

_DISALLOWED_TOKENS = re.compile(r"(?i)(≤|≥|=|at\s+or|no\s+(?:more|less))")
_CONNECTOR_RE = re.compile(r"(?i)\b(?:and/or|and|or|;|,)\b")
_TOKEN_RE = re.compile(
    r"""(?ix)
    (?P<prefix>hold\s+(?:for|if)\s+)?
    (?P<measure>sbp|systolic|hr|pulse|heart\s*rate)
    (?:\s*(?:is|to)?\s*)?
    (?:
        (?P<symbol><|>)\s*(?P<symbol_value>\d{2,3}) |
        (?P<word_op>less\s*than|greater\s*than)\s*(?P<word_value>\d{2,3})
    )
    """,
)


@dataclass(slots=True)
class RuleSpec:
    """Normalized representation of a strict hold rule."""

    kind: str
    threshold: int
    description: str

    @classmethod
    def from_kwargs(cls, **kwargs: object) -> "RuleSpec":
        """Adapter for legacy keyword arguments."""
        if "rule_kind" in kwargs and "kind" not in kwargs:
            kwargs["kind"] = kwargs.pop("rule_kind")
        return cls(**kwargs)


def _normalize_measure(raw: str) -> Optional[str]:
    lowered = raw.lower()
    if lowered in {"sbp", "systolic"}:
        return "SBP"
    if lowered in {"hr", "pulse", "heart rate"}:
        return "HR"
    return None


def _comparator_from_tokens(symbol: Optional[str], word_op: Optional[str]) -> Optional[str]:
    if symbol in {"<", ">"}:
        return symbol
    if word_op:
        word_lower = word_op.replace(" ", "").lower()
        if "less" in word_lower:
            return "<"
        if "greater" in word_lower:
            return ">"
    return None


def parse_rule_text(text: str) -> List[RuleSpec]:
    """Parse ``text`` for strict SBP/HR hold rules."""
    if not text or _DISALLOWED_TOKENS.search(text):
        return []

    specs: List[RuleSpec] = []
    hold_context = False
    cursor = 0

    for match in _TOKEN_RE.finditer(text):
        prefix = match.group("prefix")
        measure_raw = match.group("measure")
        symbol = match.group("symbol")
        symbol_value = match.group("symbol_value")
        word_op = match.group("word_op")
        word_value = match.group("word_value")

        preceding_fragment = text[cursor : match.start()]

        if prefix:
            hold_context = True
        elif _CONNECTOR_RE.search(preceding_fragment):
            # connector tokens keep whichever context was already in effect
            pass
        else:
            normalized = preceding_fragment.strip().lower()
            if normalized:
                hold_context = "hold" in normalized

        cursor = match.end()

        if not hold_context:
            continue

        comparator = _comparator_from_tokens(symbol, word_op)
        if comparator is None:
            continue

        value_token = symbol_value or word_value
        if value_token is None:
            continue
        try:
            threshold = int(value_token)
        except ValueError:
            continue

        measure = _normalize_measure(measure_raw)
        if measure is None:
            continue

        description = f"Hold if {measure} {comparator} {threshold}"
        specs.append(RuleSpec(kind=f"{measure}{comparator}", threshold=threshold, description=description))
        cursor = match.end()

    return specs


__all__ = ["RuleSpec", "parse_rule_text"]
