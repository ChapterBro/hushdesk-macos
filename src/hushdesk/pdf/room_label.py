from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
from typing import Optional


@dataclass
class LabeledRoom:
    room_base: Optional[int]   # 3-digit room number
    bed: Optional[int]         # 1 or 2
    source: str                # 'labels' or 'unknown'


_ROOM_RE = re.compile(r'\bRoom\s+(\d{3})\b', re.IGNORECASE)
_LOC_RE  = re.compile(r'\b(Location|Bed)\s+([12AB])\b', re.IGNORECASE)


def _load_building_master() -> dict:
    # Best-effort; do not fail audit if missing
    candidates = [
        Path(__file__).resolve().parents[2] / "config" / "building_master_mac.json",
        Path(__file__).resolve().parents[2] / "config" / "building_master.json",
    ]
    for p in candidates:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


def _hall_ranges_from_master(master: dict) -> dict[str, set[int]]:
    """
    Returns hall -> set of base room ints (e.g., { 'MORTON': {401,402,...} })
    Accepts multiple possible structures; best-effort.
    """
    halls: dict[str, set[int]] = {}
    if isinstance(master, dict):
        for hall, rooms in master.items():
            s: set[int] = set()
            if isinstance(rooms, list):
                for r in rooms:
                    # allow '404-1', '404', 404
                    if isinstance(r, str):
                        m = re.search(r'(\d{3})', r)
                        if m: s.add(int(m.group(1)))
                    elif isinstance(r, int):
                        s.add(r)
            elif isinstance(rooms, dict):
                # map of room -> beds
                for k in rooms.keys():
                    m = re.search(r'(\d{3})', str(k))
                    if m: halls.setdefault(str(hall).upper(), set()).add(int(m.group(1)))
                continue
            halls[str(hall).upper()] = s
    return halls


def parse_room_and_bed_from_text(full_text: str) -> LabeledRoom:
    """
    Extract from page header text (already canonical).
    Only trusts explicit labels Room/Location/Bed. Never free-form digits.
    """
    rb = None
    bed = None
    m_room = _ROOM_RE.search(full_text)
    if m_room:
        try:
            rb = int(m_room.group(1))
        except Exception:
            rb = None
    m_loc = _LOC_RE.search(full_text)
    if m_loc:
        v = m_loc.group(2).upper()
        if v in ("1","A"): bed = 1
        elif v in ("2","B"): bed = 2
    return LabeledRoom(room_base=rb, bed=bed, source="labels" if (rb or bed) else "unknown")


def validate_room(hall_name: Optional[str], labeled: LabeledRoom) -> LabeledRoom:
    """
    If Building Master available and hall known, ensure room_base in hall set.
    Otherwise return labeled as-is.
    """
    if labeled.room_base is None:
        return labeled
    master = _load_building_master()
    ranges = _hall_ranges_from_master(master)
    if hall_name:
        hall_key = str(hall_name).upper()
        allowed = ranges.get(hall_key)
        if isinstance(allowed, set) and allowed and (labeled.room_base not in allowed):
            # invalidate if not in hall
            return LabeledRoom(room_base=None, bed=labeled.bed, source=labeled.source)
    return labeled


def format_room_label(labeled: LabeledRoom) -> Optional[str]:
    if labeled.room_base is None or labeled.bed not in (1,2):
        return None
    # A→-1, B→-2 :: we’ve mapped 1→-1, 2→-2
    bed_suffix = "-1" if labeled.bed == 1 else "-2"
    return f"{labeled.room_base}{bed_suffix}"
