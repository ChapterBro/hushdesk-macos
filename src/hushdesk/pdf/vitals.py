"""Extract blood pressure and heart rate vitals from MAR column bands."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Union

try:  # pragma: no cover - PyMuPDF optional when tests run
    import fitz  # type: ignore
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore

from .geometry import normalize_rect

BP_RE = re.compile(r"(?i)\b(?:bp\s*)?(\d{2,3})\s*/\s*(\d{2,3})\b")
HR_RE = re.compile(r"(?i)\b(?:hr|pulse|heart\s*rate|p)\s*(\d{2,3})\b")
PLAIN_HR_RE = re.compile(r"\b(\d{2,3})\b")

VitalsResult = Dict[str, Optional[Union[str, int]]]


def parse_bp_token(text: str) -> Optional[str]:
    """Return ``SBP/DBP`` if ``text`` contains a blood pressure reading."""

    if not text:
        return None
    normalized = _normalize_token(text)
    match = BP_RE.search(normalized)
    if match:
        systolic, diastolic = match.groups()
        return f"{int(systolic)}/{int(diastolic)}"

    collapsed = normalized.replace(" ", "")
    if "/" in collapsed:
        parts = collapsed.split("/")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            return f"{int(parts[0])}/{int(parts[1])}"
    return None


def parse_hr_token(text: str) -> Optional[int]:
    """Return an integer heart-rate value discovered in ``text``."""

    if not text:
        return None

    normalized = _normalize_token(text)
    match = HR_RE.search(normalized)
    if match:
        return int(match.group(1))

    plain_match = PLAIN_HR_RE.search(normalized)
    if plain_match:
        return int(plain_match.group(1))
    return None


def extract_vitals_in_band(
    page: "fitz.Page", x0: float, x1: float, y0: float, y1: float
) -> VitalsResult:
    """Return BP/HR vitals found within the provided rectangle."""

    if fitz is None:
        return {"bp": None, "hr": None}

    nx0, ny0, nx1, ny1 = normalize_rect((x0, y0, x1, y1))
    rect = fitz.Rect(nx0, ny0, nx1, ny1)
    try:
        text = page.get_text("dict", clip=rect)
    except RuntimeError:
        return {"bp": None, "hr": None}

    fragments: List[str] = []
    for block in text.get("blocks", []):
        for line in block.get("lines", []):
            span_texts = [str(span.get("text", "")) for span in line.get("spans", []) if span.get("text")]
            if not span_texts:
                continue
            fragments.append("".join(span_texts))

    combined = "\n".join(fragments)
    bp_value = parse_bp_token(combined)
    hr_value = parse_hr_token(combined)

    if bp_value is None:
        for fragment in fragments:
            bp_value = parse_bp_token(fragment)
            if bp_value is not None:
                break

    if hr_value is None:
        for fragment in fragments:
            hr_value = parse_hr_token(fragment)
            if hr_value is not None:
                break

    return {"bp": bp_value, "hr": hr_value}


def _normalize_token(value: str) -> str:
    replaced = value.replace("\n", " ").replace("\r", " ").strip()
    compressed = " ".join(replaced.split())
    return compressed
