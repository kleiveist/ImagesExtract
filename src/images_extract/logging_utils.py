"""Central logging setup without import-time filesystem side effects."""

from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(
    *,
    console_enabled: bool = True,
    file_enabled: bool = False,
    log_directory: Path | None = None,
    verbose: bool = False,
) -> logging.Logger:
    logger = logging.getLogger("images_extract")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    new_handlers: list[logging.Handler] = []

    try:
        if console_enabled:
            console = logging.StreamHandler()
            console.setFormatter(logging.Formatter("%(message)s"))
            new_handlers.append(console)

        if file_enabled:
            if log_directory is None:
                raise ValueError("log_directory is required when file logging is enabled")
            log_directory.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(
                log_directory / "images-extract.log",
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            new_handlers.append(file_handler)

        if not new_handlers:
            new_handlers.append(logging.NullHandler())
    except Exception:
        for handler in new_handlers:
            handler.close()
        raise

    for handler in tuple(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    for handler in new_handlers:
        logger.addHandler(handler)
    logger.propagate = False
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    return logger
