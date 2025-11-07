"""PyInstaller runtime hook to silence deprecated pkg_resources warning."""

from __future__ import annotations

import warnings

warnings.filterwarnings("ignore", message="pkg_resources is deprecated.*", category=UserWarning)

