"""
Instagram client - one browser, one page, every API call made from inside it.

Why a browser at all: Instagram flags requests that do not look like its own web app
(Playwright's `context.request` and plain `requests` get 429s quickly). Running `fetch()`
from a real page on www.instagram.com gives every call the browser's TLS fingerprint,
the session cookies (same origin) and the headers the web app itself sends.

Compared with the previous version this client:
- launches Chromium once per run instead of once per step (5+ launches before);
- checks the session on the same page the API calls are made from;
- paces calls with a jittered delay and backs off on 429 / "please wait";
- tries the web app's own endpoint (www.instagram.com/api/v1) first and falls back
  to i.instagram.com, the host the original code used.
"""

import json
import random
import time
from typing import Any, Callable, Dict, Optional

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

IG_APP_ID = "936619743392459"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
API_HOSTS = ("https://www.instagram.com", "https://i.instagram.com")

_FETCH_JS = """async ([url, appId]) => {
    try {
        const csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || "";
        const headers = {"x-ig-app-id": appId, "x-requested-with": "XMLHttpRequest"};
        if (csrf) headers["x-csrftoken"] = csrf;
        const res = await fetch(url, {headers, credentials: "include"});
        return {status: res.status, text: await res.text()};
    } catch (e) {
        return {status: 0, error: e.toString()};
    }
}"""


class InstagramError(Exception):
    """Raised when Instagram refuses a request for good (auth, not found, private)."""


class SessionInvalid(InstagramError):
    """The session cookie is missing, expired or logged out."""


class InstagramClient:
    """
    Context manager holding one Playwright browser for a whole run.

    Usage:
        with InstagramClient(session_id, log=print) as ig:
            data = ig.api_get("/api/v1/users/web_profile_info/?username=nasa")
    """

    def __init__(self,
                 session_id: str,
                 rate_limit_delay: float = 1.0,
                 headless: bool = True,
                 user_agent: str = DEFAULT_USER_AGENT,
                 timeout_ms: int = 30000,
                 max_retries: int = 3,
                 log: Callable[[str], None] = print,
                 should_stop: Callable[[], bool] = lambda: False):
        self.session_id = session_id or ""
        self.rate_limit_delay = max(0.0, float(rate_limit_delay))
        self.headless = headless
        self.user_agent = user_agent
        self.timeout_ms = timeout_ms
        self.max_retries = max_retries
        self.log = log
        self.should_stop = should_stop

        self._pw = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._last_call = 0.0
        self._host_index = 0  # which API host currently works
        self.requests_made = 0

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def __enter__(self) -> "InstagramClient":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def open(self) -> None:
        if not self.session_id:
            raise SessionInvalid("No Instagram session id configured")

        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(
            headless=self.headless,
            args=["--disable-dev-shm-usage"],
        )
        self.context = self.browser.new_context(
            user_agent=self.user_agent,
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
        )
        self.context.set_default_timeout(self.timeout_ms)
        self.context.add_cookies([{
            "name": "sessionid",
            "value": self.session_id,
            "domain": ".instagram.com",
            "path": "/",
            "secure": True,
            "httpOnly": True,
            "sameSite": "Lax",
        }])
        self.page = self.context.new_page()

    def close(self) -> None:
        for closer in (lambda: self.browser and self.browser.close(),
                       lambda: self._pw and self._pw.stop()):
            try:
                closer()
            except Exception:
                pass
        self.browser = self.context = self.page = self._pw = None

    # ------------------------------------------------------------------ #
    # Session
    # ------------------------------------------------------------------ #

    def check_session(self) -> Dict[str, Any]:
        """
        Load the home page once (this also sets csrftoken and the other cookies the web app
        expects) and verify that the session is logged in.

        Returns basic info about the logged-in account when available.
        Raises SessionInvalid otherwise.
        """
        try:
            self.page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
            # Give the SPA a moment to render either the feed or the login form
            self.page.wait_for_timeout(2500)
        except Exception as e:
            raise InstagramError(f"Could not open instagram.com: {e}")

        login_form = self.page.locator('input[name="username"], input[name="email"]')
        cookies = {c["name"]: c["value"] for c in self.context.cookies("https://www.instagram.com")}
        if "sessionid" not in cookies or login_form.first.is_visible():
            raise SessionInvalid("Session ID is invalid or expired (login form shown)")

        return {"user_id": cookies.get("ds_user_id", "")}

    # ------------------------------------------------------------------ #
    # API
    # ------------------------------------------------------------------ #

    def _pace(self) -> None:
        """Wait so that calls are at least rate_limit_delay apart, with +-30% jitter."""
        if self.rate_limit_delay <= 0:
            return
        target = self.rate_limit_delay * random.uniform(0.7, 1.3)
        wait = target - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)

    def _fetch(self, url: str) -> Dict[str, Any]:
        self._pace()
        self._last_call = time.monotonic()
        self.requests_made += 1
        return self.page.evaluate(_FETCH_JS, [url, IG_APP_ID])

    def api_get(self, path: str) -> Dict[str, Any]:
        """
        GET an Instagram private-web API path (e.g. "/api/v1/feed/user/123/") and return JSON.

        Retries 429 / 5xx with exponential backoff, switches host once if the current one
        fails, and raises InstagramError for permanent failures.
        """
        last_error = ""
        hosts_tried = 0
        attempt = 0

        while hosts_tried < len(API_HOSTS):
            if self.should_stop():
                raise InstagramError("Stopped")

            url = API_HOSTS[self._host_index] + path
            result = self._fetch(url)
            status = result.get("status", 0)
            text = result.get("text", "") or ""

            if status == 200:
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    last_error = f"non-JSON response from {url}"
                else:
                    if data.get("status") == "fail":
                        last_error = data.get("message", "request failed")
                    else:
                        return data
            elif status in (401, 403):
                body = text[:300]
                if "login_required" in body or "checkpoint" in body:
                    raise SessionInvalid(f"Instagram asks to log in again ({status})")
                last_error = f"HTTP {status}: {body}"
            elif status == 404:
                raise InstagramError(f"Not found: {path}")
            elif status == 429 or status >= 500 or "wait a few minutes" in text.lower():
                attempt += 1
                if attempt <= self.max_retries:
                    delay = min(120, 10 * (2 ** (attempt - 1))) * random.uniform(0.8, 1.2)
                    self.log(f"⏳ Rate limited ({status}), waiting {delay:.0f}s "
                             f"(attempt {attempt}/{self.max_retries})")
                    time.sleep(delay)
                    continue
                last_error = f"HTTP {status} after {self.max_retries} retries"
            else:
                last_error = f"HTTP {status} {result.get('error', '')} {text[:200]}".strip()

            # Try the other host once before giving up
            hosts_tried += 1
            attempt = 0
            self._host_index = (self._host_index + 1) % len(API_HOSTS)

        raise InstagramError(f"{path}: {last_error}")

    def page_html(self, url: str) -> str:
        """Load a full page in a temporary tab and return its HTML (used only as a fallback)."""
        self._pace()
        self._last_call = time.monotonic()
        self.requests_made += 1
        tab = self.context.new_page()
        try:
            response = tab.goto(url, wait_until="networkidle")
            return response.text() if response else tab.content()
        finally:
            tab.close()
