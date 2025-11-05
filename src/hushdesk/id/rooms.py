"""Room and hall resolution helpers."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Tuple

from hushdesk._paths import resource_path

ROOM_BED_PATTERN = re.compile(r"\b([1-4]\d{2})\s*[-/ ]?\s*([12])\b")
ROOM_ONLY_PATTERN = re.compile(r"\b([1-4]\d{2})\b")
DEFAULT_MASTER_PATH = "config/building_master_mac.json"


@lru_cache(maxsize=4)
def load_building_master(path: str = DEFAULT_MASTER_PATH) -> Dict[str, object]:
    """Load and cache the building master JSON."""
    resolved = resource_path(path)
    with resolved.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    default_bed = str(payload.get("defaults", {}).get("bed_if_unspecified", "-1"))
    if not default_bed.startswith("-"):
        default_bed = f"-{default_bed}"

    rooms: Dict[str, Dict[str, object]] = {}
    hall_by_code: Dict[int, str] = {}
    for hall in payload.get("halls", []):
        hall_name = str(hall.get("name", "")).strip()
        hall_code = int(hall.get("code", 0))
        hall_short = hall_name.replace(" Hall", "") if hall_name.endswith(" Hall") else hall_name
        hall_by_code[hall_code] = hall_short
        for room in hall.get("rooms", []):
            rooms[str(room)] = {"hall_code": hall_code, "hall": hall_short}

    return {
        "rooms": rooms,
        "default_bed": default_bed,
        "hall_by_code": hall_by_code,
    }


def resolve_room_from_block(
    spans: Iterable[Dict[str, object]],
    master: Dict[str, object],
) -> Optional[Tuple[str, str]]:
    """Resolve room-bed text from ``spans`` using ``master`` data."""
    rooms: Dict[str, Dict[str, object]] = master.get("rooms", {})  # type: ignore[assignment]
    default_bed: str = master.get("default_bed", "-1")  # type: ignore[assignment]
    hall_by_code: Dict[int, str] = master.get("hall_by_code", {})  # type: ignore[assignment]

    matches: List[Tuple[str, str]] = []
    for span in spans:
        text = str(span.get("text", "")) if isinstance(span, dict) else ""
        if not text:
            continue
        for match in ROOM_BED_PATTERN.finditer(text):
            room = match.group(1)
            bed = match.group(2)
            candidate = f"{room}-{bed}"
            info = rooms.get(candidate)
            if info:
                hall_code = int(info.get("hall_code", 0))
                hall_name = str(info.get("hall") or hall_by_code.get(hall_code, ""))
                matches.append((candidate, hall_name))
    if matches:
        return matches[0]

    for span in spans:
        text = str(span.get("text", "")) if isinstance(span, dict) else ""
        if not text:
            continue
        for match in ROOM_ONLY_PATTERN.finditer(text):
            room = match.group(1)
            candidate = f"{room}{default_bed}"
            info = rooms.get(candidate)
            if not info:
                continue
            hall_code = int(info.get("hall_code", 0) or (int(room) // 100) * 100)
            hall_name = str(info.get("hall") or hall_by_code.get(hall_code, ""))
            return candidate, hall_name

    return None
