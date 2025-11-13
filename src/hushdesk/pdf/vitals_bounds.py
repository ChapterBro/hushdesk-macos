from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

SBP_MIN, SBP_MAX = 70, 230
HR_MIN, HR_MAX = 39, 125


@dataclass
class GateStats:
    sbp_gated: int = 0
    hr_gated: int = 0


def _toi(value) -> Optional[int]:
    try:
        return int(round(float(value)))
    except Exception:
        return None


def gate_sbp(value) -> Tuple[Optional[int], bool]:
    v = _toi(value)
    if v is None or v < SBP_MIN or v > SBP_MAX:
        return None, True
    return v, False


def gate_hr(value) -> Tuple[Optional[int], bool]:
    v = _toi(value)
    if v is None or v < HR_MIN or v > HR_MAX:
        return None, True
    return v, False


__all__ = ["GateStats", "HR_MIN", "HR_MAX", "SBP_MIN", "SBP_MAX", "gate_hr", "gate_sbp"]
