"""Helpers for normalizing MAR hour labels into canonical slot identifiers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True, frozen=True)
class Slot:
    slot_id: str
    start_min: Optional[int]
    end_min: Optional[int]
    label: str


_RE_RANGE_12 = re.compile(
    r"""(?ix)
    ^
    (?P<start_h>\d{1,2})(?::(?P<start_m>[0-5]\d))?\s*(?P<start_ampm>a|p)m?
    \s*[-–—]\s*
    (?P<end_h>\d{1,2})(?::(?P<end_m>[0-5]\d))?\s*(?P<end_ampm>a|p)?m?
    $
    """
)

_RE_RANGE_HHMM = re.compile(r"^(?P<start_h>\d{1,2}):?(?P<start_m>[0-5]\d)?\s*[-–—]\s*(?P<end_h>\d{1,2}):?(?P<end_m>[0-5]\d)?$")
_RE_POINT_HHMM = re.compile(r"^(?P<hour>[01]?\d|2[0-3]):?(?P<minute>[0-5]\d)$")
_RE_POINT_12 = re.compile(r"^(?P<hour>\d{1,2})\s*(?P<ampm>a|p)m?$", re.IGNORECASE)
_RE_BUCKET = re.compile(r"^(AM|PM|HS)$", re.IGNORECASE)

_BUCKET_RANGES = {
    "AM": (6 * 60, 11 * 60 + 59),
    "PM": (12 * 60, 19 * 60 + 59),
    "HS": (20 * 60, 23 * 60 + 59),
}


def normalize(raw: str) -> Optional[Slot]:
    """Return a canonical slot for ``raw`` when the text resembles a time label."""

    if raw is None:
        return None
    text = " ".join(str(raw).strip().split())
    if not text:
        return None

    bucket = _RE_BUCKET.fullmatch(text)
    if bucket:
        label = bucket.group(1).upper()
        start_min, end_min = _BUCKET_RANGES[label]
        return Slot(slot_id=label, start_min=start_min, end_min=end_min, label=text)

    normalized = text.replace("—", "-").replace("–", "-").replace("−", "-")

    match = _RE_RANGE_12.fullmatch(normalized)
    if match:
        start_min = _time12_to_min(
            int(match.group("start_h")),
            int(match.group("start_m") or 0),
            match.group("start_ampm"),
        )
        end_ampm = match.group("end_ampm") or match.group("start_ampm")
        end_inferred = match.group("end_ampm") is None
        end_min = _time12_to_min(
            int(match.group("end_h")),
            int(match.group("end_m") or 0),
            end_ampm,
        )
        if (
            end_inferred
            and match.group("start_ampm")
            and match.group("start_ampm").lower() == "p"
            and end_min <= start_min
        ):
            # 8pm-1 => treat trailing hour as AM when it would otherwise regress.
            end_min = _time12_to_min(int(match.group("end_h")), int(match.group("end_m") or 0), "a")
        slot_id = _slot_range_id(start_min, end_min)
        return Slot(slot_id=slot_id, start_min=start_min, end_min=end_min, label=text)

    match = _RE_RANGE_HHMM.fullmatch(normalized)
    if match:
        start_min = _hhmm_to_min(int(match.group("start_h")), _safe_int(match.group("start_m")))
        end_min = _hhmm_to_min(int(match.group("end_h")), _safe_int(match.group("end_m")))
        slot_id = _slot_range_id(start_min, end_min)
        return Slot(slot_id=slot_id, start_min=start_min, end_min=end_min, label=text)

    match = _RE_POINT_HHMM.fullmatch(normalized)
    if match:
        minutes = _hhmm_to_min(int(match.group("hour")), int(match.group("minute")))
        slot_id = _slot_point_id(minutes)
        return Slot(slot_id=slot_id, start_min=minutes, end_min=minutes, label=text)

    match = _RE_POINT_12.fullmatch(normalized)
    if match:
        minutes = _time12_to_min(int(match.group("hour")), 0, match.group("ampm"))
        slot_id = _slot_point_id(minutes)
        return Slot(slot_id=slot_id, start_min=minutes, end_min=minutes, label=text)

    return None


def _slot_range_id(start: int, end: int) -> str:
    return f"RANGE_{start // 60:02d}{start % 60:02d}_{end // 60:02d}{end % 60:02d}"


def _slot_point_id(point: int) -> str:
    return f"POINT_{point // 60:02d}{point % 60:02d}"


def _time12_to_min(hour: int, minute: int, ampm: Optional[str]) -> int:
    hh = hour % 12
    if ampm:
        ampm = ampm.lower()
        if ampm.startswith("p"):
            hh += 12
        elif ampm.startswith("a") and hour == 12:
            hh = 0
    total = (hh * 60 + (minute or 0)) % (24 * 60)
    return total


def _hhmm_to_min(hour: int, minute: Optional[int]) -> int:
    return (hour % 24) * 60 + (minute or 0)


def _safe_int(value: Optional[str]) -> Optional[int]:
    return int(value) if value is not None else None


__all__ = ["Slot", "normalize"]
