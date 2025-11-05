"""Utility helpers for locating packaged resources."""

from __future__ import annotations

import sys
from pathlib import Path


def _candidate_roots() -> list[Path]:
    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if isinstance(meipass, str):
        base = Path(meipass)
        roots.append(base)
        roots.append(base / "Resources")
    module_root = Path(__file__).resolve().parents[2]
    roots.append(module_root)
    roots.append(module_root / "Resources")
    return roots


def _candidate_rel_paths(rel_path: Path) -> list[Path]:
    if rel_path.is_absolute():
        return [rel_path]
    candidates = [rel_path]
    if rel_path.parts and rel_path.parts[0] != "hushdesk":
        candidates.append(Path("hushdesk") / rel_path)
    candidates.append(Path("Resources") / rel_path)
    candidates.append(Path("Resources") / "hushdesk" / rel_path)
    return candidates


def resource_path(rel: str | Path) -> Path:
    """Return an absolute path for ``rel`` inside the bundle or repository."""
    rel_path = Path(rel)
    for root in _candidate_roots():
        for candidate in _candidate_rel_paths(rel_path):
            candidate_path = (root / candidate).resolve()
            if candidate_path.exists():
                return candidate_path
    # Fall back to best-effort join with the first root.
    primary_root = _candidate_roots()[0]
    return (primary_root / rel_path).resolve()
