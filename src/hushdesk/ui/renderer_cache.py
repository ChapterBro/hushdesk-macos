"""Process-local renderer cache used by preview_renderer."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


def _footprint(width: int, height: int) -> int:
    """Approximate RGBA footprint in bytes."""

    return max(0, int(width) * int(height) * 4)


@dataclass(frozen=True)
class CacheKey:
    """Unique identifier for a rendered MAR preview."""

    doc_sha: str
    page_index: int
    dpi: int
    region: Tuple[int, int, int, int]


class PixCache:
    """Simple LRU cache that caps total memory usage."""

    def __init__(self, max_bytes: int = 180 * 1024 * 1024):
        self.max_bytes = max_bytes
        self._bytes = 0
        self._store: "OrderedDict[CacheKey, Tuple[Any, int, int]]" = OrderedDict()

    def get(self, key: CacheKey) -> Optional[Any]:
        item = self._store.get(key)
        if item is None:
            return None
        self._store.move_to_end(key, last=True)
        return item[0]

    def put(self, key: CacheKey, value: Any, width: int, height: int) -> None:
        size = _footprint(width, height)
        if size > self.max_bytes:
            return
        if key in self._store:
            _, old_w, old_h = self._store.pop(key)
            self._bytes -= _footprint(old_w, old_h)
        self._store[key] = (value, width, height)
        self._bytes += size
        self._evict()

    def stats(self) -> Dict[str, int]:
        return {
            "items": len(self._store),
            "bytes": self._bytes,
            "cap": self.max_bytes,
        }

    def clear(self) -> None:
        self._store.clear()
        self._bytes = 0

    def _evict(self) -> None:
        while self._bytes > self.max_bytes and self._store:
            _, (_, width, height) = self._store.popitem(last=False)
            self._bytes -= _footprint(width, height)
