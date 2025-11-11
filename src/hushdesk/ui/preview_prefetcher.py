"""Background renderer prefetcher for MAR previews."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional, Sequence

from .preview_renderer import render_pdf_page

_EXECUTOR = ThreadPoolExecutor(max_workers=3)


def schedule(task: Callable[[], None]) -> None:
    """Submit ``task`` to the shared prefetch executor."""

    try:
        _EXECUTOR.submit(task)
    except Exception:
        # Prefetching is opportunistic; ignore dispatch failures.
        pass


def prefetch_neighbors(
    pdf_path: str | Path,
    page_index: int,
    *,
    span: int = 2,
    total_pages: Optional[int] = None,
    target_dpi: int = 144,
    force_landscape: bool = True,
    region: Optional[Sequence[float]] = None,
) -> None:
    """Warm the renderer cache for neighboring pages around ``page_index``."""

    if span <= 0:
        return
    source = Path(pdf_path).expanduser()
    neighbors: list[int] = []
    for offset in range(1, span + 1):
        for candidate in (page_index - offset, page_index + offset):
            if candidate < 0:
                continue
            if total_pages is not None and candidate >= total_pages:
                continue
            if candidate not in neighbors:
                neighbors.append(candidate)
    for idx in neighbors:
        schedule(
            lambda index=idx: _render_neighbor(
                source,
                index,
                target_dpi,
                force_landscape,
                region,
            )
        )


def _render_neighbor(
    pdf_path: Path,
    page_index: int,
    target_dpi: int,
    force_landscape: bool,
    region: Optional[Sequence[float]],
) -> None:
    try:
        render_pdf_page(
            pdf_path,
            page_index,
            target_dpi=target_dpi,
            force_landscape=force_landscape,
            region=region,
        )
    except Exception:
        # Rendering may fail if the page is out of bounds or the PDF is unavailable.
        pass
