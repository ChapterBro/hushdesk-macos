"""Tests for vital sign parsing utilities."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from hushdesk.pdf.vitals import (  # noqa: E402
    extract_vitals_in_band,
    extract_vitals_in_band_fallback,
    parse_bp_token,
    parse_hr_token,
)


class VitalParsingTests(unittest.TestCase):
    def test_parse_bp_token_with_newline(self) -> None:
        text = "120/\n80"
        self.assertEqual(parse_bp_token(text), "120/80")

    def test_parse_bp_token_invalid(self) -> None:
        self.assertIsNone(parse_bp_token("No BP documented"))

    def test_parse_hr_token_with_label(self) -> None:
        self.assertEqual(parse_hr_token("Pulse 78"), 78)

    def test_parse_hr_token_plain_number(self) -> None:
        self.assertIsNone(parse_hr_token("64"))

    def test_parse_hr_token_invalid(self) -> None:
        self.assertIsNone(parse_hr_token("N/A"))

    def test_fallback_extracts_bp_and_hr(self) -> None:
        sample_dict = {
            "blocks": [
                {
                    "lines": [
                        {
                            "spans": [
                                {"text": "BP 118/70 HR 74", "bbox": [100.0, 300.0, 180.0, 312.0]},
                            ]
                        },
                        {
                            "spans": [
                                {"text": "P 68", "bbox": [110.0, 350.0, 140.0, 360.0]},
                                {"text": "BP 132/82", "bbox": [150.0, 350.0, 200.0, 362.0]},
                            ]
                        },
                    ]
                }
            ]
        }

        class StubPage:
            def __init__(self, payload: dict) -> None:
                self._payload = payload

            def get_text(self, kind: str, clip: object = None) -> dict:
                if kind != "dict":
                    return {}
                return self._payload

        result = extract_vitals_in_band_fallback(StubPage(sample_dict), 90.0, 200.0, (0.0, 220.0))
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["bp"], "118/70")
        self.assertEqual(result[0]["hr"], 74)
        self.assertEqual(result[1]["bp"], "132/82")
        self.assertEqual(result[1]["hr"], 68)

    def test_extract_vitals_uses_column_fallback(self) -> None:
        fallback_dict = {
            "blocks": [
                {
                    "lines": [
                        {
                            "spans": [
                                {"text": "BP 120/78", "bbox": [100.0, 310.0, 160.0, 322.0]},
                                {"text": "Pulse 70", "bbox": [100.0, 324.0, 150.0, 336.0]},
                            ]
                        },
                        {
                            "spans": [
                                {"text": "BP 138/82", "bbox": [100.0, 360.0, 160.0, 372.0]},
                            ]
                        },
                    ]
                }
            ]
        }

        class DummyRect:
            def __init__(self, *args: float) -> None:
                self.args = args

        class StubPage:
            def __init__(self, payload: dict) -> None:
                self._payload = payload

            def get_text(self, kind: str, clip: object = None) -> dict:
                if kind != "dict":
                    return {}
                if clip is not None:
                    return {"blocks": []}
                return self._payload

        page = StubPage(fallback_dict)
        stub_fitz = SimpleNamespace(Rect=DummyRect)
        with patch("hushdesk.pdf.vitals.fitz", stub_fitz):
            result = extract_vitals_in_band(
                page,
                90.0,
                180.0,
                300.0,
                340.0,
                dose_hint="AM",
                dose_bands={"AM": (290.0, 330.0), "PM": (340.0, 380.0)},
            )
        self.assertEqual(result["bp"], "120/78")
        self.assertEqual(result["hr"], 70)
        self.assertIn("_fallback_selected", result)


if __name__ == "__main__":
    unittest.main()
