"""Parity checks between Rust accelerators and Python fallbacks."""

from __future__ import annotations

from typing import Dict, Tuple

import pytest

from hushdesk import accel


pytestmark = pytest.mark.skipif(
    not accel.ACCEL_AVAILABLE,
    reason="Rust accelerator is not available",
)


def test_y_cluster_matches_python() -> None:
    points = [12.0, 12.2, 24.4, 36.0, 36.1, 60.0]
    bin_px = 12

    py_centers = accel._y_cluster_py(points, bin_px)
    rs_centers = list(accel.y_cluster_rs(points, bin_px))

    assert rs_centers == pytest.approx(py_centers)


def test_stitch_bp_matches_python() -> None:
    lines = ["120 /", "  80", "not digits"]

    py_value = accel._stitch_bp_py(lines)
    rs_value = accel.stitch_bp_rs(lines)

    assert rs_value == py_value


def test_select_bands_matches_python() -> None:
    centers = [(1, 100.0), (2, 200.0), (3, 400.0), (3, 402.0)]
    page_width = 612.0

    py_bands = accel._select_bands_py(centers, page_width)
    rs_bands_raw = accel.select_bands_rs(centers, page_width)
    rs_bands: Dict[int, Tuple[float, float]] = dict(rs_bands_raw)

    assert set(rs_bands) == set(py_bands)
    for day, (x0, x1) in py_bands.items():
        assert rs_bands[day][0] == pytest.approx(x0)
        assert rs_bands[day][1] == pytest.approx(x1)
