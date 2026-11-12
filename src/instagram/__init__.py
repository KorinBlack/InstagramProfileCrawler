"""
Instagram module - Core functionality for interacting with Instagram API.
"""

from .auth import InstagramAuth, SessionManager, check_session
from .client import InstagramClient, InstagramError, SessionInvalid
from .scraper import InstagramScraper, MediaRef, ScrapeOptions


__all__ = [
    "InstagramAuth",
    "SessionManager",
    "check_session",
    "InstagramClient",
    "InstagramError",
    "SessionInvalid",
    "InstagramScraper",
    "MediaRef",
    "ScrapeOptions",
]
