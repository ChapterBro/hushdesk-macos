"""TXT report writer aligned with the PRD format."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

from hushdesk.fs.exports import safe_write_text
from .model import DecisionRecord

_CENTRAL = ZoneInfo("America/Chicago")
_KIND_ORDER = ["HOLD-MISS", "HELD-APPROPRIATE", "COMPLIANT", "DC'D"]
_DOSE_ORDER = {"AM": 0, "PM": 1}


def write_report(
    records: List[DecisionRecord],
    counts: dict,
    audit_date_mmddyyyy: str,
    hall: str,
    source_basename: str,
    out_path: Path,
    notes: Optional[Iterable[str]] = None,
) -> Path:
    """Write the binder-ready TXT report to ``out_path`` and return the final path."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    split_used = any("split" in _normalize_record_notes(record.notes) for record in records)

    hall_upper = hall.upper()
    date_with_hyphen = audit_date_mmddyyyy.replace("/", "-")
    lines: List[str] = [f"Date: {date_with_hyphen}", f"Hall: {hall_upper}"]
    if source_basename:
        lines.append(f"Source: {source_basename}")
    lines.append("")

    counts_line = (
        "Counts (chips): Reviewed {reviewed} · Hold-Miss {hold_miss} · "
        "Held-Appropriate {held_app} · Compliant {compliant} · DC'D {dcd}"
    ).format(
        reviewed=counts.get("reviewed", 0),
        hold_miss=counts.get("hold_miss", 0),
        held_app=counts.get("held_appropriate", 0),
        compliant=counts.get("compliant", 0),
        dcd=counts.get("dcd", 0),
    )
    lines.append(counts_line)
    lines.append("")

    exceptions = [
        record
        for record in records
        if record.kind in {"HOLD-MISS", "HELD-APPROPRIATE"} and record.chip
    ]
    lines.append("Exceptions —")
    if exceptions:
        for record in _iter_sorted_by_room(exceptions):
            lines.append(_format_record_line(record))
    else:
        lines.append("Hold-Miss: 0 (no exceptions)")

    lines.append("")
    lines.append("All Reviewed —")
    grouped: Dict[str, List[DecisionRecord]] = {kind: [] for kind in _KIND_ORDER}
    fallback_bucket: List[DecisionRecord] = []
    for record in records:
        if record.kind in grouped:
            grouped[record.kind].append(record)
        else:
            fallback_bucket.append(record)

    for kind in _KIND_ORDER:
        for record in _iter_sorted_by_room(grouped[kind]):
            lines.append(_format_record_line(record))

    if fallback_bucket:
        for record in _iter_sorted_by_room(fallback_bucket):
            lines.append(_format_record_line(record))

    note_lines: List[str] = []
    seen_notes: set[str] = set()
    vitals_seen: set[tuple[str, str]] = set()
    split_noted = False

    for note in notes or []:
        raw = str(note).strip()
        if not raw:
            continue
        sanitized, had_split = _sanitize_note_text(raw)
        if had_split:
            split_noted = True
        vitals_key = _vitals_note_key(sanitized)
        if vitals_key:
            if vitals_key in vitals_seen:
                continue
            vitals_seen.add(vitals_key)
        if sanitized in seen_notes:
            continue
        note_lines.append(sanitized)
        seen_notes.add(sanitized)

    if split_used or split_noted:
        aggregate = "AM/PM labels missing (split)"
        if aggregate not in seen_notes:
            note_lines.append(aggregate)
            seen_notes.add(aggregate)

    if note_lines:
        lines.append("")
        for text in note_lines:
            lines.append(f"Notes — {text}")

    lines.append("")
    generated_stamp = datetime.now(_CENTRAL).strftime("%m/%d/%Y %H:%M")
    lines.append(f"Generated: {generated_stamp} (Central)")

    content = "\n".join(lines)
    return safe_write_text(out_path, content)


def _iter_sorted_by_room(records: Iterable[DecisionRecord]) -> Iterable[DecisionRecord]:
    return sorted(records, key=_room_sort_key)


def _room_sort_key(record: DecisionRecord) -> tuple:
    room = record.room_bed or "Unknown"
    room_key = (room.lower() == "unknown", room)
    dose_key = _DOSE_ORDER.get(record.dose, 0)
    return (room_key, dose_key, record.rule_text)


def _format_record_line(record: DecisionRecord) -> str:
    dose_label = record.dose
    prefix = f"{record.kind} — {record.room_bed} ({dose_label}) — "

    if record.kind == "DC'D":
        reason = record.dcd_reason or "Due cell DC'd"
        return f"{prefix}{reason}"

    reason = _compose_reason(record)
    return f"{prefix}{reason}"


def _compose_reason(record: DecisionRecord) -> str:
    rule_text = _ensure_hold_if_prefix(_strip_source_suffix(record.rule_text))
    parts: List[str] = [rule_text]

    vital_text = record.vital_text.strip()
    if vital_text:
        parts.append(vital_text)

    state_detail = str(record.extras.get("state_detail", "")).strip()
    if state_detail:
        parts.append(state_detail)
    elif record.kind == "HELD-APPROPRIATE" and record.code is not None:
        parts.append(f"code {record.code}")

    reason = "; ".join(part for part in parts if part)

    if record.kind == "COMPLIANT" and not record.chip:
        suffix = " (reviewed)"
        if reason:
            reason = f"{reason}{suffix}"
        else:
            reason = f"Hold if strict rule documented{suffix}"

    return reason


def _normalize_record_notes(notes: Optional[str]) -> set[str]:
    if not notes:
        return set()
    tokens = []
    for piece in notes.split(";"):
        token = piece.strip().lower()
        if token:
            tokens.append(token)
    return set(tokens)


def _sanitize_note_text(text: str) -> tuple[str, bool]:
    """Return note text without inline ``(split)`` markers and whether one was removed."""

    lower_text = text.lower()
    has_split = "(split" in lower_text
    if not has_split:
        return text, False

    cleaned = re.sub(r"\s*\(split\)", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    cleaned = cleaned.replace("( ", "(").replace(" )", ")")
    return cleaned, True


_SOURCE_SUFFIX_RE = re.compile(r"\s*(?:[;|])?\s*Source:\s*.+$", re.IGNORECASE)
_VITALS_NOTE_RE = re.compile(
    r"(?i)^vitals\s+missing\s*\(unexpected\)\s*—\s*(?P<room>[^()]+?)\s*\((?P<dose>[^)]+)\)"
)


def _strip_source_suffix(text: Optional[str]) -> str:
    if not text:
        return ""
    stripped = _SOURCE_SUFFIX_RE.sub("", text).rstrip()
    if stripped:
        return stripped
    if "source:" in text.lower():
        return ""
    return text


def _ensure_hold_if_prefix(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return "Hold if strict rule documented"
    lowered = stripped.lower()
    if lowered.startswith("hold if"):
        return stripped
    return f"Hold if {stripped}"


def _vitals_note_key(text: str) -> Optional[tuple[str, str]]:
    match = _VITALS_NOTE_RE.match(text)
    if not match:
        return None
    room = match.group("room").strip()
    dose_token = match.group("dose").strip()
    if not room or not dose_token:
        return None
    dose = dose_token.split()[0].strip().upper()
    if not dose:
        return None
    return (room, dose)


__all__ = ["write_report"]
