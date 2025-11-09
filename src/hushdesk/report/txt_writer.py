"""TXT report writer aligned with the PRD format."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional
from zoneinfo import ZoneInfo

from .model import DecisionRecord

_CENTRAL = ZoneInfo("America/Chicago")
_KIND_ORDER = ["HOLD-MISS", "HELD-OK", "COMPLIANT", "DC'D"]
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
    """Write the binder-ready TXT report to ``out_path`` and return the path."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    split_used = any("split" in _normalize_record_notes(record.notes) for record in records)

    hall_upper = hall.upper()
    header = f"{audit_date_mmddyyyy} · Hall: {hall_upper} · Source: {source_basename}"
    counts_line = (
        "Reviewed: {reviewed} · Hold-Miss: {hold_miss} · Held-OK: {held_ok} · "
        "Compliant: {compliant} · DC'D: {dcd}"
    ).format(
        reviewed=counts.get("reviewed", 0),
        hold_miss=counts.get("hold_miss", 0),
        held_ok=counts.get("held_ok", 0),
        compliant=counts.get("compliant", 0),
        dcd=counts.get("dcd", 0),
    )

    lines: List[str] = [header, counts_line, ""]

    exceptions = [record for record in records if record.kind in {"HOLD-MISS", "HELD-OK"}]
    lines.append("Exceptions —")
    if exceptions:
        for record in _iter_sorted(exceptions):
            lines.append(_format_record_line(record))
    else:
        lines.append("Hold-Miss: 0 (no exceptions)")

    lines.append("")
    lines.append("All Reviewed —")
    sorted_records = list(_iter_sorted(records))
    for kind in _KIND_ORDER:
        for record in sorted_records:
            if record.kind == kind:
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

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def _iter_sorted(records: Iterable[DecisionRecord]) -> Iterable[DecisionRecord]:
    return sorted(records, key=_record_sort_key)


def _record_sort_key(record: DecisionRecord) -> tuple:
    room = record.room_bed or "Unknown"
    room_key = (room.lower() == "unknown", room)
    dose_key = _DOSE_ORDER.get(record.dose, 0)
    kind_key = _KIND_ORDER.index(record.kind) if record.kind in _KIND_ORDER else len(_KIND_ORDER)
    return (room_key, dose_key, kind_key, record.rule_text)


def _format_record_line(record: DecisionRecord) -> str:
    dose_label = record.dose

    if record.kind == "DC'D":
        reason = record.dcd_reason or "X in due cell"
        return f"{record.kind} — {record.room_bed} ({dose_label}) — {reason}"

    rule_text = _strip_source_suffix(record.rule_text)
    base = f"{record.kind} — {record.room_bed} ({dose_label}) — {rule_text}"
    detail_parts: List[str] = []
    vital_text = record.vital_text.strip()
    if vital_text:
        detail_parts.append(vital_text)
    if record.kind == "HELD-OK" and record.code is not None:
        detail_parts.append(f"| code {record.code}")

    if not detail_parts:
        return base

    if detail_parts[0].startswith("|"):
        return f"{base} {detail_parts[0]}"

    if len(detail_parts) == 1:
        return f"{base}; {detail_parts[0]}"

    formatted = "; ".join(part for part in detail_parts if not part.startswith("|"))
    suffix = " ".join(part for part in detail_parts if part.startswith("|"))

    message = f"{base}; {formatted}"
    if suffix:
        message = f"{message} {suffix}"
    return message


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
