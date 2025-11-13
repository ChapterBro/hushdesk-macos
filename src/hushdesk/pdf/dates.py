"""Helpers for resolving audit dates from MAR PDF filenames."""

from __future__ import annotations

import os
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Iterable, Pattern

from zoneinfo import ZoneInfo

CENTRAL_TZ = ZoneInfo("America/Chicago")

_FILENAME_PATTERNS: Iterable[Pattern[str]] = (
    re.compile(r"(?P<year>\d{4})[-_](?P<month>\d{2})[-_](?P<day>\d{2})"),
    re.compile(r"(?P<month>\d{2})[-_](?P<day>\d{2})[-_](?P<year>\d{4})"),
)


def parse_filename_date(path: str) -> date | None:
    """Attempt to extract a date component from ``path``.

    Supports ``YYYY-MM-DD``, ``MM-DD-YYYY`` and underscore-delimited variants.
    Returns ``None`` when no recognizable pattern is found or when the value is
    not a valid calendar date.
    """

    stem = Path(path).stem
    for pattern in _FILENAME_PATTERNS:
        match = pattern.search(stem)
        if not match:
            continue
        parts = {key: int(value) for key, value in match.groupdict().items()}
        year = parts["year"]
        month = parts["month"]
        day = parts["day"]
        try:
            return date(year=year, month=month, day=day)
        except ValueError:
            continue
    return None


def central_prev_day(value: date) -> date:
    """Return the previous calendar day evaluated in the America/Chicago zone."""

    start_of_day = datetime.combine(value, time.min, tzinfo=CENTRAL_TZ)
    previous = start_of_day - timedelta(days=1)
    return previous.date()


def format_mmddyyyy(value: date) -> str:
    """Return ``value`` formatted as ``MM/DD/YYYY``."""

    return f"{value.month:02d}/{value.day:02d}/{value.year:04d}"


def resolve_audit_date(filename: Path) -> date:
    """Resolve the effective audit date for ``filename``.

    Filename dates take precedence over any future printed-on values. When no
    filename date is found, default to the previous Central day relative to now.
    """

    parsed = parse_filename_date(filename.name)
    if parsed:
        return central_prev_day(parsed)

    today_central = datetime.now(tz=CENTRAL_TZ).date()
    return central_prev_day(today_central)


def dev_override_date() -> date | None:
    """Return a developer-specified audit date via HUSHDESK_DEV_DATE (YYYY-MM-DD)."""

    value = os.environ.get("HUSHDESK_DEV_DATE")
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None
