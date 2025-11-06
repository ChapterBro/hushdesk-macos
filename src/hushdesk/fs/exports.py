"""Helpers for safe TXT/QA exports that avoid macOS TCC permission issues."""

from __future__ import annotations

import errno
import logging
import os
import re
from pathlib import Path
from typing import Final

_LOGGER = logging.getLogger(__name__)

_APP_SUPPORT: Final[Path] = Path.home() / "Library" / "Application Support" / "HushDesk"
_EXPORT_ROOT: Final[Path] = _APP_SUPPORT / "Exports"
_SAFE_CHAR_RE: Final[re.Pattern[str]] = re.compile(r"[^a-zA-Z0-9._\- ]+")
_SPACE_RE: Final[re.Pattern[str]] = re.compile(r"\s+")
_DOUBLE_DOT_RE: Final[re.Pattern[str]] = re.compile(r"\.{2,}")

_MAX_FILENAME_LEN: Final[int] = 120


def exports_dir() -> Path:
    """Return the default Exports directory, creating it if needed."""
    _EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
    return _EXPORT_ROOT


def qa_dir() -> Path:
    """Return the QA overlays directory within Application Support."""
    path = _APP_SUPPORT / "QA"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_qa_prefix(user_value: str | os.PathLike[str] | None) -> Path:
    """Normalise user-provided QA paths into a writable App Support location.

    Relative paths are treated as name hints (dropping subdirectories) and
    resolved within :func:`qa_dir`. Absolute paths are honoured when their
    parent can be created; otherwise the basename is redirected into the QA
    directory to guarantee writability.
    """

    base = qa_dir()
    if not user_value:
        return base

    candidate = Path(user_value).expanduser()
    if candidate.is_absolute():
        parent = candidate.parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
            return candidate
        except Exception:
            fallback = base / candidate.name
            fallback.parent.mkdir(parents=True, exist_ok=True)
            return fallback

    hint = candidate.name or "qa_overlay.png"
    fallback = base / hint
    fallback.parent.mkdir(parents=True, exist_ok=True)
    return fallback


def sanitize_filename(base: str) -> str:
    """Sanitize ``base`` so it is safe for filesystem use."""
    base = (base or "").strip()
    name, ext = os.path.splitext(base)
    if not name:
        name = "HushDesk"
    if ext and not ext.startswith("."):
        ext = f".{ext}"

    sanitized_name = _SAFE_CHAR_RE.sub("_", name)
    sanitized_name = _SPACE_RE.sub(" ", sanitized_name)
    sanitized_name = _DOUBLE_DOT_RE.sub(".", sanitized_name)
    sanitized_name = sanitized_name.strip(" .") or "HushDesk"

    sanitized_ext = _SAFE_CHAR_RE.sub("", ext)
    sanitized_ext = _DOUBLE_DOT_RE.sub(".", sanitized_ext)

    candidate = f"{sanitized_name}{sanitized_ext}"
    if len(candidate) <= _MAX_FILENAME_LEN:
        return candidate

    trim_len = max(0, _MAX_FILENAME_LEN - len(sanitized_ext))
    trimmed_name = sanitized_name[:trim_len].rstrip(" .") or "HushDesk"
    return f"{trimmed_name}{sanitized_ext}"


def safe_write_text(path: Path, text: str) -> Path:
    """Persist ``text`` to ``path``, falling back to Exports on TCC denials."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path
    except OSError as exc:
        if exc.errno not in (errno.EPERM, errno.EACCES):
            raise
        fallback_dir = exports_dir()
        fallback_path = fallback_dir / path.name
        _LOGGER.warning(
            "safe_write_text fallback (errno=%s) original=%s fallback=%s",
            exc.errno,
            path,
            fallback_path,
        )
        fallback_path.write_text(text, encoding="utf-8")
        return fallback_path


__all__ = ["exports_dir", "qa_dir", "resolve_qa_prefix", "sanitize_filename", "safe_write_text"]
