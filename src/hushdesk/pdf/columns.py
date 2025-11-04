"""Stub helpers for column selection and clamping."""

from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger(__name__)


def select_audit_column(audit_date: date) -> tuple[int, int] | None:
    """Stub that logs the audit date and returns ``None`` for now."""

    logger.info("Column clamp requested for audit date %s", audit_date.isoformat())
    return None
