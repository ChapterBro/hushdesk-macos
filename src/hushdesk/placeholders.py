"""Utility helpers for placeholder audit output content."""

from __future__ import annotations

import time
from pathlib import Path


def build_placeholder_output(source_pdf: Path) -> str:
    """Return a stubbed TXT payload for the audit placeholder."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "HushDesk BP Audit Placeholder",
        f"Generated: {timestamp} (Central)",
        f"Source MAR: {source_pdf.name}",
        "",
        "Hold if SBP greater than 160 — placeholder line",
        "Hold if HR less than 55 — placeholder line",
        "",
        "Reviewed: 0 | Hold-Miss: 0 | Held-OK: 0 | Compliant: 0 | DC'D: 0",
    ]
    return "\n".join(lines)
