"""TXT report writer aligned with the PRD format."""

from __future__ import annotations

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
) -> None:
    """Write the binder-ready TXT report to ``out_path``."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

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

    if notes:
        lines.append("")
        seen: set[str] = set()
        for note in notes:
            text = str(note).strip()
            if not text or text in seen:
                continue
            lines.append(f"Notes — {text}")
            seen.add(text)

    lines.append("")
    generated_stamp = datetime.now(_CENTRAL).strftime("%m/%d/%Y %H:%M")
    lines.append(f"Generated: {generated_stamp} (Central)")

    out_path.write_text("\n".join(lines), encoding="utf-8")


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
    note_tokens = _normalize_record_notes(record.notes)
    if "split" in note_tokens:
        dose_label = f"{dose_label} (split)"
    elif "fallback" in note_tokens:
        dose_label = f"{dose_label} (fallback)"

    if record.kind == "DC'D":
        reason = record.dcd_reason or "X in due cell"
        return f"{record.kind} — {record.room_bed} ({dose_label}) — {reason}"

    base = f"{record.kind} — {record.room_bed} ({dose_label}) — {record.rule_text}"
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


__all__ = ["write_report"]
