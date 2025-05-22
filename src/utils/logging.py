"""
Shared logging utility for the MCP project.

Enforces a consistent, non-colored log format across the entire application and all major dependencies
(e.g., MCP SDK, uvicorn). Ensures no log coloring or ANSI escapes are possible, for maximal uniformity.

Usage:
    from utils.logging import configure_logging, get_logger

    configure_logging() # Call once at application startup, in main.py

    logger = get_logger(__name__)
    logger.info("Some message")
"""

import logging
import sys
from typing import Optional, TextIO

_LOG_FORMAT = "%(levelname)s:     %(message)s"
_LOG_LEVEL = logging.INFO


def configure_logging(level: int = _LOG_LEVEL, stream: Optional[TextIO] = None) -> None:
    """
    Configure the root logger and all major lib loggers (uvicorn, mcp) to use a uniform, non-colored output.
    Removes any existing handlers—including those that add color or formatting.
    """
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    # Clean root handlers
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.handlers = []
    root.addHandler(handler)
    root.setLevel(level)
    # Overwrite all relevant third-party and framework loggers
    loggers_to_clean = [
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "mcp",
    ]
    for name in loggers_to_clean:
        logger = logging.getLogger(name)
        for h in list(logger.handlers):
            logger.removeHandler(h)
        logger.handlers = []
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = True  # Ensures messages always reach root handler


def get_logger(
    name: Optional[str] = None, level: Optional[int] = None
) -> logging.Logger:
    """
    Get a logger with project-wide formatting and configuration.
    """
    logger = logging.getLogger(name)
    if level is not None:
        logger.setLevel(level)
    return logger
