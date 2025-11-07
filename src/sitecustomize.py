"""Runtime-wide warning filters for CLI and packaged execution."""

from __future__ import annotations

import warnings

warnings.filterwarnings("ignore", message="pkg_resources is deprecated.*", category=UserWarning)

