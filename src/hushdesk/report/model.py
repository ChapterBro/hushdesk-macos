"""Report data structures for binder-ready TXT output."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Literal, Optional

DecisionKind = Literal["HOLD-MISS", "HELD-OK", "HELD-APPROPRIATE", "COMPLIANT", "DC'D"]


@dataclass(slots=True)
class DecisionRecord:
    """Normalized representation of a single dose decision."""

    hall: str
    date_mmddyyyy: str
    source_basename: str
    room_bed: str
    dose: Literal["AM", "PM"]
    kind: DecisionKind
    rule_text: str
    vital_text: str
    code: Optional[int]
    dcd_reason: Optional[str]
    notes: Optional[str] = None
    extras: Dict[str, object] = field(default_factory=dict)
    chip: bool = False
    preview: Optional[Dict[str, object]] = None


__all__ = ["DecisionRecord", "DecisionKind"]
