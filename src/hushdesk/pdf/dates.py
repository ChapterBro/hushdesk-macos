"""Helpers for resolving audit dates from MAR PDF filenames."""

from __future__ import annotations

import logging
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

    override = dev_override_date()
    if override:
        return override

    parsed = parse_filename_date(filename.name)
    if parsed:
        return central_prev_day(parsed)

    today_central = datetime.now(tz=CENTRAL_TZ).date()
    return central_prev_day(today_central)


# Developer override for audit date (optional, safe default)
_DEV_OVERRIDE_ENV = "HUSHDESK_AUDIT_DATE_MMDDYYYY"
_MMDDYYYY_RE = re.compile(r"\s*(\d{2})/(\d{2})/(\d{4})\s*")
logger = logging.getLogger(__name__)

def dev_override_date():
    """Optional developer override for audit date."""
    raw_value = os.getenv(_DEV_OVERRIDE_ENV)
    if not raw_value:
        return None
    m = _MMDDYYYY_RE.fullmatch(raw_value)
    if not m:
        logger.warning(
            "Ignoring invalid %s=%r; expected MM/DD/YYYY",
            _DEV_OVERRIDE_ENV,
            raw_value,
        )
        return None
    month, day, year = (int(g) for g in m.groups())
    try:
        from datetime import date
        return date(year, month, day)
    except Exception:
        logger.warning("Ignoring out-of-range %s=%r", _DEV_OVERRIDE_ENV, raw_value)
        return None
