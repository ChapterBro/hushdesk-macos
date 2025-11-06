from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

APP_SUPPORT = Path.home() / "Library" / "Application Support" / "HushDesk"
LOG_DIR = APP_SUPPORT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "hushdesk.log"


def get_logger(name: str = "hushdesk") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=1_500_000, backupCount=5, encoding="utf-8"
    )
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


def log_path() -> Path:
    return LOG_FILE
