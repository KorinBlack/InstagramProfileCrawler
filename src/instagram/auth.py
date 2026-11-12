"""
Instagram session helpers.

The browser work now lives in `client.InstagramClient`; this module keeps the old names
(`SessionManager`, `InstagramAuth`) for scripts such as example_usage.py.
"""

import os
from typing import Any, Dict

from dotenv import load_dotenv

from .client import InstagramClient, InstagramError


def mask_secret(value: str) -> str:
    """Show only the ends of a session id: 'abcd…wxyz'."""
    if not value:
        return ""
    if len(value) <= 10:
        return "•" * len(value)
    return f"{value[:4]}…{value[-4:]}"


def check_session(session_id: str, headless: bool = True) -> Dict[str, Any]:
    """
    Open a browser, verify the session and close it.

    Returns {"valid": bool, "user_id": str, "error": str}.
    """
    try:
        with InstagramClient(session_id, rate_limit_delay=0, headless=headless, log=lambda _m: None) as ig:
            info = ig.check_session()
            return {"valid": True, "user_id": info.get("user_id", ""), "error": ""}
    except InstagramError as e:
        return {"valid": False, "user_id": "", "error": str(e)}
    except Exception as e:  # browser not installed, network down, ...
        return {"valid": False, "user_id": "", "error": f"{type(e).__name__}: {e}"}


class SessionManager:
    """Holds the session id. No browser is started until something asks for it."""

    def __init__(self, session_id: str = ""):
        load_dotenv()
        self.session_id = session_id or os.getenv("INSTAGRAM_SESSION_ID", "")

    def check(self) -> bool:
        result = check_session(self.session_id)
        if not result["valid"]:
            print(f"✗ Session invalid: {result['error']}")
        return result["valid"]

    def client(self, **kwargs) -> InstagramClient:
        return InstagramClient(self.session_id, **kwargs)


# Backward-compatible alias
InstagramAuth = SessionManager
