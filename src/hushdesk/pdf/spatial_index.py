from __future__ import annotations

from bisect import bisect_left
from typing import Iterable, List, Optional, Sequence, Tuple


class SpatialWordIndex:
    """Spatial index over words with .text and .center=(x,y)."""

    def __init__(self, entries: Sequence[Tuple[float, float, object]]):
        self._rows = list(entries)
        self._ys = [row[0] for row in self._rows]

    @classmethod
    def build(cls, words: Iterable[object]) -> Optional["SpatialWordIndex"]:
        entries: List[Tuple[float, float, object]] = []
        for word in words:
            text = getattr(word, "text", "").strip()
            if not text:
                continue
            center = getattr(word, "center", None)
            if not center or len(center) < 2:
                continue
            y = round(float(center[1]), 1)
            x = float(center[0])
            entries.append((y, x, word))
        if not entries:
            return None
        entries.sort(key=lambda item: (item[0], item[1]))
        return cls(entries)

    def neighbors(self, x0: float, y0: float, max_dy: float = 2.0, max_dx: float = 110.0):
        y_query = round(float(y0), 1)
        lower = round(y_query - max_dy, 1)
        idx = bisect_left(self._ys, lower)
        hits = []
        upper = y_query + max_dy
        while idx < len(self._rows) and self._rows[idx][0] <= upper:
            row_y, row_x, word = self._rows[idx]
            if abs(row_y - y_query) <= max_dy and abs(row_x - x0) <= max_dx:
                hits.append(word)
            idx += 1
        return hits


__all__ = ["SpatialWordIndex"]
