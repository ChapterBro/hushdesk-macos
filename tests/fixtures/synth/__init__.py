"""Synthetic fixtures for headless worker tests."""

from .pages import DummyPage
from .worker import (
    ALLOWED_CODE_RULE_TEXT,
    BASE_BLOCK_BBOX,
    BASE_COLUMN_BAND,
    BASE_ROOM_INFO,
    HR_RULE_TEXT,
    build_row_bands,
)

__all__ = [
    "DummyPage",
    "ALLOWED_CODE_RULE_TEXT",
    "BASE_BLOCK_BBOX",
    "BASE_COLUMN_BAND",
    "BASE_ROOM_INFO",
    "HR_RULE_TEXT",
    "build_row_bands",
]
