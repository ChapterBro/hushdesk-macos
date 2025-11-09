"""Minimal page shims for exercising worker logic without PyMuPDF."""

from __future__ import annotations

from typing import Any, Dict


class DummyPage:
    """Stub page that mimics the PyMuPDF API shape used in tests."""

    def __init__(self, text_map: Dict[str, Any] | None = None) -> None:
        self._text_map = text_map or {}

    def get_text(self, kind: str, clip: Any = None) -> Any:  # pragma: no cover - trivial
        return self._text_map.get(kind, {})
