"""
Safe placeholder token helpers for MAR due-cell parsing.

These utilities extract vitals or coded states from the limited signals that
remain available in the tracer sandbox.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable, Tuple

logger = logging.getLogger(__name__)

_BP_PAIR = re.compile(r"\b(\d{2,3})\s*/\s*(\d{2,3})\b")
_NUMBER = re.compile(r"\b(\d{2,3})\b")
_PULSE = re.compile(r"\b(\d{2,3})\s*(?:bpm|/min)?\b", re.IGNORECASE)
_X_TOKEN = re.compile(r"(?i)\bx+\b")


def _textify(blob: object) -> str:
    if isinstance(blob, str):
        return blob
    if isinstance(blob, Iterable):
        parts: list[str] = []
        for item in blob:
            text = getattr(item, "text", None)
            if isinstance(text, str):
                stripped = text.strip()
                if stripped:
                    parts.append(stripped)
            elif isinstance(item, str):
                stripped = item.strip()
                if stripped:
                    parts.append(stripped)
        return " ".join(parts)
    return str(blob)


def bp_values(blob: object) -> int | None:
    """Return the systolic BP value (if any) detected in ``blob``."""

    text = _textify(blob)
    match = _BP_PAIR.search(text)
    if match:
        return int(match.group(1))
    match = _NUMBER.search(text)
    if match:
        return int(match.group(1))
    return None


def pulse_value(blob: object) -> int | None:
    """Return the pulse/HR value (if any) detected in ``blob``."""

    text = _textify(blob)
    match = _PULSE.search(text)
    if match:
        return int(match.group(1))
    return None


def cell_state(blob: object, *, has_drawn_cross: bool = False) -> Tuple[str, int | None]:
    """
    Infer a due-cell state and optional numeric code from ``blob``.

    The placeholder implementation surfaces a small subset of state markers so
    the tracer can keep logging telemetry without ImportErrors.
    """

    text = _textify(blob)
    lowered = text.lower()
    state = "EMPTY"
    if has_drawn_cross or _X_TOKEN.search(text):
        state = "DCD"
    elif "hold" in lowered or "code" in lowered:
        state = "CODE"
    elif "given" in lowered or "admin" in lowered or "ok" in lowered:
        state = "GIVEN"
    elif lowered.strip():
        state = "TEXT"

    code = None
    match = _NUMBER.search(text)
    if match:
        try:
            code = int(match.group(1))
        except ValueError:
            logger.debug("mar_tokens stub: failed to parse code from %r", match.group(1))
            code = None

    return state, code


__all__ = ["bp_values", "cell_state", "pulse_value"]
