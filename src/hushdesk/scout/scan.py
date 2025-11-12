"""Stub scan module used to satisfy worker imports in headless test runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from hushdesk.pdf.columns import ColumnBand


@dataclass(slots=True)
class ScoutCandidate:
    page: int
    room_bed: str | None = None
    dose: str | None = None
    has_code: bool = False
    has_time: bool = False
    rule_kinds: Sequence[str] = ()


def scan_candidates(doc, audit_date, bands: Sequence[ColumnBand]) -> List[ScoutCandidate]:
    # Phase-6 headless runs do not rely on scout results; return empty candidates.
    return []


__all__ = ["ScoutCandidate", "scan_candidates"]
