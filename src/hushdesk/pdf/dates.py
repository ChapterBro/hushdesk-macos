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
logger = logging.getLogger(__name__)

_MMDDYYYY_ENV = "HUSHDESK_AUDIT_DATE_MMDDYYYY"
_MM_DD_YYYY_ENV = "HUSHDESK_AUDIT_DATE_MM_DD_YYYY"
_MMDDYYYY_RE = re.compile(r"\s*(\d{2})/(\d{2})/(\d{4})\s*")

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


def dev_override_date() -> date | None:
    """Return an override audit date sourced from environment variables.

    Reads ``HUSHDESK_AUDIT_DATE_MMDDYYYY`` or ``HUSHDESK_AUDIT_DATE_MM_DD_YYYY``.
    Values must be ``MM/DD/YYYY``. Invalid inputs are logged and ignored.
    """

    raw = os.getenv(_MMDDYYYY_ENV) or os.getenv(_MM_DD_YYYY_ENV)
    if not raw:
        return None

    match = _MMDDYYYY_RE.fullmatch(raw)
    if not match:
        logger.warning("Ignoring invalid audit date override: %r", raw)
        return None

    month, day, year = (int(part) for part in match.groups())
    try:
        return date(year=year, month=month, day=day)
    except ValueError:
        logger.warning("Ignoring out-of-range audit date override: %r", raw)
        return None


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
