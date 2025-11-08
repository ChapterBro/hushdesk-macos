"""Strict rule normalization for canonical MAR parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Sequence

from .mupdf_canon import CanonWord

# Hard rejects
_REJECT_CHARS = {"≤", "≥", "="}
_REJECT_PATTERNS = [
    r"\b(?:≤|≥|=)\b",
    r"\bat\s+or\b",
    r"\bequal\b",
    r"\bno\s+(?:less|more)\s+than\b",
    r"\bglucose\b",
    r"\bsugar\b",
    r"\bstool",
    r"\bloose\s+stools?\b",
    r"\bper\s+rn\b",
    r"\bnursing\s+judg(?:e|)ment\b",
]

_SBP_TARGET = r"(?:sbp|systolic)"
_HR_TARGET = r"(?:pulse|hr)"
_SBP_BLOCK = r"pulse|hr"
_HR_BLOCK = r"sbp|systolic"
_LT_COMPARATOR = r"(?:<|less\s+than)"
_GT_COMPARATOR = r"(?:>|greater\s+than)"


def _strict_pattern(target: str, blocker: str, comparator: str) -> re.Pattern[str]:
    block = ""
    if blocker:
        block = rf"(?:(?!\b(?:{blocker})\b).)*?"
    return re.compile(rf"\b({target})\b{block}(?:{comparator})\s*(\d{{2,3}})", re.IGNORECASE)


# Strict accepts (case-insensitive)
SBP_LT = _strict_pattern(_SBP_TARGET, _SBP_BLOCK, _LT_COMPARATOR)
SBP_GT = _strict_pattern(_SBP_TARGET, _SBP_BLOCK, _GT_COMPARATOR)
HR_LT = _strict_pattern(_HR_TARGET, _HR_BLOCK, _LT_COMPARATOR)
HR_GT = _strict_pattern(_HR_TARGET, _HR_BLOCK, _GT_COMPARATOR)

_LINE_BREAK_RE = re.compile(r"[\r\n]+")
_HYPHEN_BREAK_RE = re.compile(r"-\s*(?:\r?\n)+\s*")
_WHITESPACE_RE = re.compile(r"\s+")
_BULLET_RE = re.compile(r"[•·]+")


@dataclass(slots=True)
class RuleSet:
    """Normalized strict hold rules captured from MAR text."""

    sbp_lt: Optional[int] = None
    sbp_gt: Optional[int] = None
    hr_lt: Optional[int] = None
    hr_gt: Optional[int] = None
    strict: bool = False

    def as_dict(self) -> dict[str, int]:
        result: dict[str, int] = {}
        if self.sbp_lt is not None:
            result["sbp_lt"] = self.sbp_lt
        if self.sbp_gt is not None:
            result["sbp_gt"] = self.sbp_gt
        if self.hr_lt is not None:
            result["hr_lt"] = self.hr_lt
        if self.hr_gt is not None:
            result["hr_gt"] = self.hr_gt
        result["strict"] = self.strict
        return result


def normalize_rule_text(text: str) -> RuleSet:
    """Return a strict ``RuleSet`` parsed from freeform ``text``."""

    flattened = _flatten_block_text(text)
    return _parse_rule_text(flattened)


def rules_from_words(words: Sequence[CanonWord]) -> RuleSet:
    """Return strict rules normalized from ``words`` text."""

    text = " ".join(word.text for word in words if word.text.strip())
    return normalize_rule_text(text)


def parse_rules(text: str) -> RuleSet:
    """Return strict rules parsed from medication block text."""

    flattened = _flatten_block_text(text)
    return _parse_rule_text(flattened)


def _parse_rule_text(text: str) -> RuleSet:
    cleaned = _collapse_spaces(text)
    if not cleaned:
        return RuleSet()

    if _has_rejects(cleaned):
        return RuleSet(strict=False)

    sbp_lt = _extract_threshold(SBP_LT, cleaned)
    sbp_gt = _extract_threshold(SBP_GT, cleaned)
    hr_lt = _extract_threshold(HR_LT, cleaned)
    hr_gt = _extract_threshold(HR_GT, cleaned)

    strict = any(value is not None for value in (sbp_lt, sbp_gt, hr_lt, hr_gt))
    if not strict:
        return RuleSet()

    return RuleSet(
        sbp_lt=sbp_lt,
        sbp_gt=sbp_gt,
        hr_lt=hr_lt,
        hr_gt=hr_gt,
        strict=True,
    )


def _has_rejects(text: str) -> bool:
    raw = text or ""
    if any(char in raw for char in _REJECT_CHARS):
        return True
    lowered = raw.lower()
    return any(re.search(pattern, lowered) for pattern in _REJECT_PATTERNS)


def _extract_threshold(pattern: re.Pattern[str], text: str) -> Optional[int]:
    match = pattern.search(text)
    if not match:
        return None
    try:
        return int(match.group(2))
    except (ValueError, IndexError):
        return None


def _collapse_spaces(text: str) -> str:
    if not text:
        return ""
    return _WHITESPACE_RE.sub(" ", text).strip()


def _flatten_block_text(text: str) -> str:
    raw = text or ""
    if not raw:
        return ""
    without_hyphen_breaks = _HYPHEN_BREAK_RE.sub("", raw)
    without_bullets = _BULLET_RE.sub(" ", without_hyphen_breaks)
    collapsed_lines = _LINE_BREAK_RE.sub(" ", without_bullets)
    collapsed_spaces = _WHITESPACE_RE.sub(" ", collapsed_lines)
    cleaned = collapsed_spaces.strip()
    return cleaned


__all__ = ["RuleSet", "normalize_rule_text", "rules_from_words", "parse_rules"]
