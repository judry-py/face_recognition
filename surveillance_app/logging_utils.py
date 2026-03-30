from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import PROJECT_ROOT

LOG_FILE_PATH = PROJECT_ROOT / "surveillance_app.log"


def setup_logging(log_path: str | Path = LOG_FILE_PATH) -> None:
    root_logger = logging.getLogger()
    if getattr(root_logger, "_surveillance_logging_ready", False):
        return

    path = Path(log_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    file_handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)
    root_logger._surveillance_logging_ready = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
