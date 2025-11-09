"""
Safe placeholder for the MAR scout scanning helpers.

The real implementation lives on another branch; this stub simply keeps the
audit worker imports satisfied so the tracer can run without crashing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence


@dataclass(slots=True)
class ScoutCandidate:
    """Minimal representation of a PDF candidate produced by the scout scan."""

    path: Path
    score: float = 0.0


def scan_candidates(sources: Iterable[Path] | None = None) -> Sequence[ScoutCandidate]:
    """
    Return an empty list for compatibility.

    The tracer flow does not require scout pre-filtering, so the placeholder
    implementation simply yields no candidates.
    """

    return []


__all__ = ["ScoutCandidate", "scan_candidates"]
