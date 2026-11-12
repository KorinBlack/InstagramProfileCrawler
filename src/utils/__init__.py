"""
Utils module - Logging, retry logic, and statistics.
"""

import sys

from .logger import Logger


def safe_console() -> None:
    """Never crash on characters the console cannot encode (emoji on a cp1252 Windows console)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
from .retry import RetryHandler
from .stats import StatisticsTracker

__all__ = [
    "safe_console",
    "Logger",
    "RetryHandler",
    "StatisticsTracker",
]
