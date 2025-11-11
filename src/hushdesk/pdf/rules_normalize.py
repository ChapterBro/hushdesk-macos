"""Strict rule normalization for canonical MAR parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Iterator, List, Optional, Sequence, Tuple, Union

from .mupdf_canon import CanonWord


class RuleSource(str, Enum):
    """Origin metadata for vitals hold rules."""

    DEFAULT = "default"
    PARSED = "parsed"
    REJECT = "reject"
    NONE = "none"


class Severity(str, Enum):
    """Severity bucket for parsed rules."""

    WARN = "warn"


@dataclass(frozen=True, slots=True)
class Rule:
    """Concrete rule used when evaluating vitals (SBP/HR only)."""

    id: str
    expr: str
    severity: Severity
    source: RuleSource
    version: str
    vital: str
    comparator: str
    threshold: int


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
DEFAULT_RULE_VERSION = "default:v1"
PARSED_RULE_VERSION = "strict:v1"


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
    rules: Tuple[Rule, ...] = field(default_factory=tuple)
    strict: bool = False
    source: str = RuleSource.NONE.value
    version: str = ""

    def __iter__(self) -> Iterator[Rule]:
        return iter(self.rules)

    def as_rules(self) -> List[Rule]:
        return list(self.rules)

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {}
        if self.sbp_lt is not None:
            result["sbp_lt"] = self.sbp_lt
        if self.sbp_gt is not None:
            result["sbp_gt"] = self.sbp_gt
        if self.hr_lt is not None:
            result["hr_lt"] = self.hr_lt
        if self.hr_gt is not None:
            result["hr_gt"] = self.hr_gt
        result["strict"] = self.strict
        if self.source:
            result["source"] = self.source
        if self.version:
            result["version"] = self.version
        return result

    @classmethod
    def from_rules(
        cls,
        rules: Sequence[Rule],
        *,
        source: str | RuleSource | None = None,
        version: str | None = None,
    ) -> RuleSet:
        rule_list = list(rules)
        if not rule_list:
            return cls()
        sbp_lt: Optional[int] = None
        sbp_gt: Optional[int] = None
        hr_lt: Optional[int] = None
        hr_gt: Optional[int] = None
        for rule in rule_list:
            if rule.vital == "SBP":
                if rule.comparator == "<":
                    sbp_lt = _select_threshold(sbp_lt, rule.threshold, "<")
                elif rule.comparator == ">":
                    sbp_gt = _select_threshold(sbp_gt, rule.threshold, ">")
            elif rule.vital == "HR":
                if rule.comparator == "<":
                    hr_lt = _select_threshold(hr_lt, rule.threshold, "<")
                elif rule.comparator == ">":
                    hr_gt = _select_threshold(hr_gt, rule.threshold, ">")
        resolved_source = _coerce_source(source or rule_list[0].source)
        resolved_version = version or rule_list[0].version
        return cls(
            sbp_lt=sbp_lt,
            sbp_gt=sbp_gt,
            hr_lt=hr_lt,
            hr_gt=hr_gt,
            rules=tuple(rule_list),
            strict=True,
            source=resolved_source.value,
            version=resolved_version,
        )


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


def evaluate_vitals(
    vitals_iter: Iterable[object],
    rules: Optional[Union[RuleSet, Sequence[Rule], Rule]] = None,
) -> List[dict[str, object]]:
    """Evaluate vitals for each slot-row across ``rules`` with row-level scoping."""

    normalized_rules = _coerce_rules_sequence(rules)
    if not normalized_rules:
        return []

    decisions: List[dict[str, object]] = []
    seen: set[Tuple[str, object]] = set()

    for row in vitals_iter:
        slot_label = (_row_value(row, "slot_label") or _row_value(row, "slot") or "").strip() or "UNKNOWN"
        slot_row = _row_value(row, "slot_row")
        slot_id = _row_value(row, "slot_id")
        sbp = _coerce_vital(_row_value(row, "sbp"))
        hr = _coerce_vital(_row_value(row, "hr"))
        for rule in normalized_rules:
            value = sbp if rule.vital == "SBP" else hr
            if value is None:
                continue
            if rule.comparator == ">" and value <= rule.threshold:
                continue
            if rule.comparator == "<" and value >= rule.threshold:
                continue
            row_key = slot_row if slot_row not in (None, "") else slot_label or slot_id or f"row-{id(row)}"
            dedup_key = (rule.id, row_key)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            decisions.append(
                {
                    "expr": rule.expr,
                    "rule_id": rule.id,
                    "slot_label": slot_label,
                    "slot_row": slot_row,
                    "slot_id": slot_id,
                    "sbp": sbp,
                    "hr": hr,
                    "value": value,
                    "vital": rule.vital,
                    "threshold": rule.threshold,
                    "comparator": rule.comparator,
                    "source": rule.source.value,
                    "version": rule.version,
                    "severity": rule.severity.value,
                }
            )

    return decisions


def _parse_rule_text(text: str) -> RuleSet:
    cleaned = _collapse_spaces(text)
    if not cleaned:
        return RuleSet(source=RuleSource.NONE.value, version="")

    if _has_rejects(cleaned):
        return RuleSet(strict=False, source=RuleSource.REJECT.value, version="")

    sbp_lt = _extract_threshold(SBP_LT, cleaned)
    sbp_gt = _extract_threshold(SBP_GT, cleaned)
    hr_lt = _extract_threshold(HR_LT, cleaned)
    hr_gt = _extract_threshold(HR_GT, cleaned)

    rules = _rules_from_thresholds(
        sbp_lt,
        sbp_gt,
        hr_lt,
        hr_gt,
        source=RuleSource.PARSED,
        version=PARSED_RULE_VERSION,
    )
    if not rules:
        return RuleSet(source=RuleSource.NONE.value, version="")

    return RuleSet(
        sbp_lt=sbp_lt,
        sbp_gt=sbp_gt,
        hr_lt=hr_lt,
        hr_gt=hr_gt,
        rules=rules,
        strict=True,
        source=RuleSource.PARSED.value,
        version=PARSED_RULE_VERSION,
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


def _rules_from_thresholds(
    sbp_lt: Optional[int],
    sbp_gt: Optional[int],
    hr_lt: Optional[int],
    hr_gt: Optional[int],
    *,
    source: RuleSource,
    version: str,
) -> Tuple[Rule, ...]:
    rules: List[Rule] = []
    if sbp_lt is not None:
        rules.append(_make_rule("SBP", "<", sbp_lt, source=source, version=version))
    if sbp_gt is not None:
        rules.append(_make_rule("SBP", ">", sbp_gt, source=source, version=version))
    if hr_lt is not None:
        rules.append(_make_rule("HR", "<", hr_lt, source=source, version=version))
    if hr_gt is not None:
        rules.append(_make_rule("HR", ">", hr_gt, source=source, version=version))
    return tuple(rules)


def _make_rule(vital: str, comparator: str, threshold: int, *, source: RuleSource, version: str) -> Rule:
    suffix = "lt" if comparator == "<" else "gt"
    rule_id = f"{vital.lower()}_{suffix}_{threshold}"
    expr = f"{vital}{comparator}{threshold}"
    return Rule(
        id=rule_id,
        expr=expr,
        severity=Severity.WARN,
        source=source,
        version=version,
        vital=vital,
        comparator=comparator,
        threshold=threshold,
    )


def _select_threshold(current: Optional[int], candidate: int, comparator: str) -> int:
    if current is None:
        return candidate
    if comparator == "<":
        return min(current, candidate)
    if comparator == ">":
        return max(current, candidate)
    return candidate


def _coerce_source(value: str | RuleSource) -> RuleSource:
    if isinstance(value, RuleSource):
        return value
    lowered = str(value or "").lower()
    for option in RuleSource:
        if option.value == lowered:
            return option
    return RuleSource.NONE


def _coerce_rules_sequence(
    rules: Optional[Union[RuleSet, Sequence[Rule], Rule]],
) -> List[Rule]:
    if rules is None:
        return list(default_rules())
    if isinstance(rules, Rule):
        return [rules]
    if isinstance(rules, RuleSet):
        result = rules.as_rules()
        return result or list(default_rules())
    try:
        collected: List[Rule] = []
        for item in rules:  # type: ignore[operator]
            if isinstance(item, Rule):
                collected.append(item)
            elif isinstance(item, RuleSet):
                collected.extend(item.as_rules())
        if not collected:
            return list(default_rules())
        return collected
    except TypeError:
        return list(default_rules())


def _row_value(row: object, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    if hasattr(row, key):
        return getattr(row, key)
    getter = getattr(row, "get", None)
    if callable(getter):
        try:
            return getter(key)
        except Exception:
            return None
    return None


def _coerce_vital(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(round(value))
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


__all__ = [
    "Rule",
    "RuleSet",
    "RuleSource",
    "Severity",
    "default_rules",
    "evaluate_vitals",
    "normalize_rule_text",
    "parse_rules",
    "rules_from_words",
]

_DEFAULT_RULESET = RuleSet(
    sbp_gt=140,
    hr_lt=60,
    hr_gt=110,
    rules=_rules_from_thresholds(
        None,
        140,
        60,
        110,
        source=RuleSource.DEFAULT,
        version=DEFAULT_RULE_VERSION,
    ),
    strict=True,
    source=RuleSource.DEFAULT.value,
    version=DEFAULT_RULE_VERSION,
)


def default_rules() -> RuleSet:
    """Return the minimal default rule thresholds for vitals evaluation."""

    return RuleSet(
        sbp_lt=_DEFAULT_RULESET.sbp_lt,
        sbp_gt=_DEFAULT_RULESET.sbp_gt,
        hr_lt=_DEFAULT_RULESET.hr_lt,
        hr_gt=_DEFAULT_RULESET.hr_gt,
        rules=_DEFAULT_RULESET.rules,
        strict=_DEFAULT_RULESET.strict,
        source=_DEFAULT_RULESET.source,
        version=_DEFAULT_RULESET.version,
    )
