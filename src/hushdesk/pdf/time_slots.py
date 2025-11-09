"""
Safe placeholder helpers for mapping MAR time slot labels to canonical IDs.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import re

logger = logging.getLogger(__name__)

_CLEAN_RE = re.compile(r"\s+")


@dataclass(slots=True)
class SlotToken:
    """Normalized representation of a MAR time slot label."""

    raw_label: str
    normalized: str
    slot_id: str


def _normalize_label(label: str) -> str:
    cleaned = (label or "").strip().lower()
    cleaned = cleaned.replace("–", "-").replace("—", "-").replace("−", "-")
    cleaned = cleaned.replace(":", "")
    cleaned = _CLEAN_RE.sub("", cleaned)
    return cleaned


def normalize(label: str | None) -> SlotToken | None:
    """
    Return a SlotToken with deterministic ``slot_id`` for ``label``.

    The placeholder logic simply lowercases the value, strips whitespace, and
    replaces punctuation so that down-stream caches get stable identifiers.
    """

    if not label:
        return None

    normalized = _normalize_label(label)
    if not normalized:
        return None

    slot_id = f"slot::{normalized}"
    logger.debug("time_slots stub normalized %r -> %s", label, slot_id)
    return SlotToken(raw_label=label, normalized=normalized, slot_id=slot_id)


__all__ = ["SlotToken", "normalize"]
