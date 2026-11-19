"""Logging setup for the tracker.

One rotating log file plus console output. Call :func:`configure_logging` once
at process start-up (the CLI does this for you).
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
LOG_FILE_NAME = "crypto_tracking.log"


def configure_logging(
    project_folder: Path,
    level: str = "INFO",
    *,
    log_to_file: bool = True,
    log_to_console: bool = True,
) -> logging.Logger:
    """Configure the root logger and return it.

    Existing handlers are removed so repeated calls (for example in tests or
    when the Flask reloader is used) do not duplicate log lines.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    numeric_level = logging.getLevelName(level.upper())
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO
    root.setLevel(numeric_level)

    formatter = logging.Formatter(LOG_FORMAT)

    if log_to_console:
        console = logging.StreamHandler()
        console.setLevel(numeric_level)
        console.setFormatter(formatter)
        root.addHandler(console)

    if log_to_file:
        log_dir = project_folder / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / LOG_FILE_NAME,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    # Flask's development server is chatty; keep it at warnings unless debugging.
    logging.getLogger("werkzeug").setLevel(logging.DEBUG if numeric_level <= logging.DEBUG else logging.WARNING)
    return root
