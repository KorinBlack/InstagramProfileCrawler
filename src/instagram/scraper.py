"""
Instagram scraper - posts (all pages), story highlights and current stories.

Every network call goes through one InstagramClient (one browser for the whole run).
API endpoints are tried first; the original HTML-parsing method is kept as a fallback
for highlights, so nothing that worked before is lost.
"""

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Set

from .client import InstagramClient, InstagramError

# media_type values used by the Instagram API
MEDIA_IMAGE = 1
MEDIA_VIDEO = 2
MEDIA_CAROUSEL = 8


@dataclass
class MediaRef:
    """One downloadable image."""
    id: str            # media pk (unique, stable -> used as filename)
    url: str
    source: str        # "post", "highlight" or "story"
    caption: str = ""
    taken_at: int = 0
    width: int = 0
    height: int = 0
    code: str = ""     # post shortcode, if any
    parent_id: str = ""  # carousel / highlight id
    is_video_cover: bool = False

    @property
    def filename(self) -> str:
        return f"{self.source}_{self.id}.jpg"

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["filename"] = self.filename
        return data


@dataclass
class ScrapeOptions:
    max_posts: int = 0                 # 0 = all posts
    include_posts: bool = True
    include_highlights: bool = True
    include_stories: bool = False      # current 24h stories
    include_video_covers: bool = False  # take the cover frame of videos/reels
    known_post_ids: Optional[Set[str]] = None  # stop paging once only known posts appear
    page_size: int = 33


def best_candidate(item: Dict[str, Any]) -> Dict[str, Any]:
    """Return the largest image candidate of a media item."""
    candidates = (item.get("image_versions2") or {}).get("candidates") or []
    if not candidates:
        return {}
    return max(candidates, key=lambda c: (c.get("width") or 0) * (c.get("height") or 0))


def _caption_text(item: Dict[str, Any]) -> str:
    caption = item.get("caption")
    if isinstance(caption, dict):
        return caption.get("text", "") or ""
    return ""


def extract_media(item: Dict[str, Any], source: str, include_video_covers: bool = False,
                  caption: Optional[str] = None, parent_id: str = "") -> List[MediaRef]:
    """Turn one API media item (image, carousel or video) into MediaRefs."""
    caption = _caption_text(item) if caption is None else caption
    media_type = item.get("media_type")
    refs: List[MediaRef] = []

    if media_type == MEDIA_CAROUSEL:
        parent = str(item.get("pk") or item.get("id") or "")
        for child in item.get("carousel_media") or []:
            refs.extend(extract_media(child, source, include_video_covers,
                                      caption=caption, parent_id=parent))
        for ref in refs:
            ref.code = item.get("code", "") or ref.code  # the post's link is the parent's
            ref.taken_at = ref.taken_at or int(item.get("taken_at") or 0)
        return refs

    if media_type == MEDIA_VIDEO and not include_video_covers:
        return refs

    candidate = best_candidate(item)
    if not candidate.get("url"):
        return refs

    media_id = str(item.get("pk") or item.get("id") or "").split("_")[0]
    refs.append(MediaRef(
        id=media_id,
        url=candidate["url"],
        source=source,
        caption=caption,
        taken_at=int(item.get("taken_at") or 0),
        width=int(candidate.get("width") or 0),
        height=int(candidate.get("height") or 0),
        code=item.get("code", "") or "",
        parent_id=parent_id,
        is_video_cover=media_type == MEDIA_VIDEO,
    ))
    return refs


class InstagramScraper:
    """Scrapes one profile through an open InstagramClient."""

    def __init__(self, client: InstagramClient, log: Callable[[str], None] = print,
                 should_stop: Callable[[], bool] = lambda: False):
        self.client = client
        self.log = log
        self.should_stop = should_stop

    # ------------------------------------------------------------------ #
    # Profile
    # ------------------------------------------------------------------ #

    def get_profile(self, username: str) -> Dict[str, Any]:
        data = self.client.api_get(f"/api/v1/users/web_profile_info/?username={username}")
        user = (data.get("data") or {}).get("user")
        if not user:
            raise InstagramError(f"Profile @{username} not found")
        return user

    # ------------------------------------------------------------------ #
    # Posts (paginated)
    # ------------------------------------------------------------------ #

    def iter_post_items(self, username: str, user_id: str, opts: ScrapeOptions) -> Iterable[Dict[str, Any]]:
        """Yield raw feed items, page by page, until the end, max_posts or known posts."""
        count = 0
        max_id = ""
        page = 0
        known = opts.known_post_ids or set()

        while True:
            if self.should_stop():
                return
            page += 1
            if page == 1:
                # The web app's own first call (and the one the original code used)
                path = f"/api/v1/feed/user/{username}/username/?count={opts.page_size}"
            else:
                path = f"/api/v1/feed/user/{user_id}/?count={opts.page_size}&max_id={max_id}"

            try:
                feed = self.client.api_get(path)
            except InstagramError as e:
                if page > 1:
                    # Fallback: same endpoint as page 1, with the cursor
                    feed = self.client.api_get(
                        f"/api/v1/feed/user/{username}/username/?count={opts.page_size}&max_id={max_id}")
                else:
                    raise e

            items = feed.get("items") or []
            new_on_page = 0
            for item in items:
                item_id = str(item.get("pk") or item.get("id") or "").split("_")[0]
                if item_id not in known:
                    new_on_page += 1
                yield item
                count += 1
                if opts.max_posts and count >= opts.max_posts:
                    return

            self.log(f"  page {page}: {len(items)} posts ({count} total)")

            if known and items and new_on_page == 0:
                self.log("  reached posts already downloaded in a previous run, stopping")
                return
            max_id = feed.get("next_max_id") or ""
            if not feed.get("more_available") or not max_id or not items:
                self.feed_complete = True
                return

    # ------------------------------------------------------------------ #
    # Highlights and stories
    # ------------------------------------------------------------------ #

    def get_highlight_ids(self, user_id: str, username: str) -> List[Dict[str, Any]]:
        """Return [{"id": "highlight:123", "title": ...}] via API, else by parsing the profile page."""
        try:
            data = self.client.api_get(f"/api/v1/highlights/{user_id}/highlights_tray/")
            tray = data.get("tray") or []
            return [{"id": str(h.get("id")), "title": h.get("title", ""),
                     "media_count": h.get("media_count", 0)} for h in tray if h.get("id")]
        except InstagramError as e:
            self.log(f"  highlights tray API failed ({e}), parsing the profile page instead")

        html = self.client.page_html(f"https://www.instagram.com/{username}/")
        ids = dict.fromkeys(re.findall(r"/stories/highlights/(\d+)/", html))
        return [{"id": f"highlight:{i}", "title": "", "media_count": 0} for i in ids]

    def get_reels_media(self, reel_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """Fetch items for several reels (highlights or a user's story) in batches."""
        result: Dict[str, List[Dict[str, Any]]] = {}
        for i in range(0, len(reel_ids), 10):
            if self.should_stop():
                break
            batch = reel_ids[i:i + 10]
            query = "&".join(f"reel_ids={rid}" for rid in batch)
            data = self.client.api_get(f"/api/v1/feed/reels_media/?{query}")
            reels = data.get("reels") or {}
            if not reels and data.get("reels_media"):
                reels = {str(r.get("id")): r for r in data["reels_media"]}
            for rid, reel in reels.items():
                result[str(rid)] = reel.get("items") or []
        return result

    def _highlight_items_from_html(self, highlight_id: str) -> List[Dict[str, Any]]:
        """Original method: parse the highlight page's embedded JSON."""
        numeric = highlight_id.split(":")[-1]
        html = self.client.page_html(f"https://www.instagram.com/stories/highlights/{numeric}/")
        content_len = re.findall(
            r'<script type="application\/json"  data-content-len="(.*)" data-sjs>.*require.*'
            r'xdt_api__v1__feed__reels_media__connection', html)[0]
        content = re.findall(r'data-content-len="' + content_len + r'" data-sjs>(.{' + content_len + r'})', html)[0]
        data = json.loads(content)
        connection = (data.get("require", {})[0][3][0].get("__bbox", {}).get("require", {})[0][3][1]
                      .get("__bbox", {}).get("result").get("data", {})
                      .get("xdt_api__v1__feed__reels_media__connection", {}))
        return (connection.get("edges", [])[0].get("node", {}) or {}).get("items", [])

    def scrape_highlights(self, user_id: str, username: str, opts: ScrapeOptions) -> List[MediaRef]:
        highlights = self.get_highlight_ids(user_id, username)
        self.log(f"⭐ {len(highlights)} highlights")
        if not highlights:
            return []

        ids = [h["id"] for h in highlights]
        try:
            reels = self.get_reels_media(ids)
        except InstagramError as e:
            self.log(f"  reels_media API failed ({e}), using highlight pages")
            reels = {}

        refs: List[MediaRef] = []
        for hid in ids:
            if self.should_stop():
                break
            items = reels.get(hid)
            if items is None:
                try:
                    items = self._highlight_items_from_html(hid)
                except Exception as e:
                    self.log(f"  ⚠ highlight {hid}: {e}")
                    continue
            for item in items:
                refs.extend(extract_media(item, "highlight", opts.include_video_covers,
                                          caption="", parent_id=hid))
        return refs

    def scrape_stories(self, user_id: str, opts: ScrapeOptions) -> List[MediaRef]:
        reels = self.get_reels_media([user_id])
        refs: List[MediaRef] = []
        for item in reels.get(str(user_id), []):
            refs.extend(extract_media(item, "story", opts.include_video_covers, caption=""))
        return refs

    # ------------------------------------------------------------------ #
    # Everything
    # ------------------------------------------------------------------ #

    def scrape(self, username: str, opts: ScrapeOptions) -> Dict[str, Any]:
        """
        Scrape a profile. Returns {"profile": {...}, "media": [MediaRef], "feed_complete": bool}.
        Parts that fail are logged and skipped, so one failing section never loses the others.
        """
        self.feed_complete = False
        self.log(f"🔍 @{username}")
        user = self.get_profile(username)
        user_id = str(user.get("id"))
        posts_total = (user.get("edge_owner_to_timeline_media") or {}).get("count", 0)
        profile = {
            "id": user_id,
            "username": user.get("username", username),
            "full_name": user.get("full_name", ""),
            "is_private": bool(user.get("is_private")),
            "followed_by_viewer": bool(user.get("followed_by_viewer")),
            "posts_count": posts_total,
            "followers": (user.get("edge_followed_by") or {}).get("count", 0),
        }
        if profile["is_private"] and not profile["followed_by_viewer"]:
            self.log("⚠ Private profile not followed by this account: only public parts are reachable")

        media: List[MediaRef] = []
        errors: List[str] = []

        if opts.include_posts:
            self.log(f"📸 Posts ({posts_total} on profile, limit: {opts.max_posts or 'all'})")
            try:
                for item in self.iter_post_items(username, user_id, opts):
                    media.extend(extract_media(item, "post", opts.include_video_covers))
            except InstagramError as e:
                errors.append(f"posts: {e}")
                self.log(f"✗ Posts: {e}")

        if opts.include_highlights and not self.should_stop():
            try:
                media.extend(self.scrape_highlights(user_id, username, opts))
            except InstagramError as e:
                errors.append(f"highlights: {e}")
                self.log(f"✗ Highlights: {e}")

        if opts.include_stories and not self.should_stop():
            try:
                stories = self.scrape_stories(user_id, opts)
                self.log(f"🕒 {len(stories)} images in current stories")
                media.extend(stories)
            except InstagramError as e:
                errors.append(f"stories: {e}")
                self.log(f"✗ Stories: {e}")

        # The same image can show up twice (e.g. a post re-shared in a highlight)
        unique: Dict[str, MediaRef] = {}
        for ref in media:
            unique.setdefault(ref.filename, ref)

        return {
            "profile": profile,
            "media": list(unique.values()),
            "feed_complete": self.feed_complete,
            "errors": errors,
        }
