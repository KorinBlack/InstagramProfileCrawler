"""
Dataset pipeline shared by the CLI and the web GUI.

Per profile, in <output_dir>/<username>/:
    1. scrape   - posts (all pages), highlights, stories, one browser for everything
    2. download - parallel, skips files already on disk (filenames are media ids)
    3. dedupe   - exact duplicates moved to _rejected/
    4. filter   - Visual AI; rejected images moved to _rejected/ with the reason
    5. optimize - optional resize / recompress
    6. caption  - .txt / .json sidecars next to each image

Nothing is deleted: rejected images can be restored from the GUI.
"""

import json
import os
import shutil
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

import requests
from PIL import Image

from .filtering.visual_ai import VisualAI
from .images.deduplicator import ImageDeduplicator
from .images.optimizer import ImageOptimizer
from .instagram.client import DEFAULT_USER_AGENT, InstagramClient, InstagramError, SessionInvalid
from .instagram.scraper import InstagramScraper, MediaRef, ScrapeOptions
from .settings import engine_api_key, engine_endpoint

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
REJECTED_DIR = "_rejected"
MANIFEST = "manifest.json"
REASONS = "reasons.json"
CAPTION_EXTENSIONS = (".txt", ".json")


class Cancelled(Exception):
    """The run was stopped by the user."""


# ---------------------------------------------------------------------- #
# Small JSON / dataset helpers (also used by the web GUI)
# ---------------------------------------------------------------------- #

def read_json(path: Path, default: Any) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path: Path, data: Any) -> None:
    """Atomic write: never leaves a half-written file behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def profile_dir(output_dir: str, username: str) -> Path:
    return Path(output_dir).expanduser() / username


def list_images(directory: Path) -> List[Path]:
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.iterdir()
                  if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS and not p.name.startswith("."))


def sidecars(image: Path) -> List[Path]:
    return [image.with_suffix(ext) for ext in CAPTION_EXTENSIONS if image.with_suffix(ext).exists()]


def reject_image(directory: Path, filename: str, reason: str, by: str, confidence: float = 0.0) -> None:
    """Move an image (and its caption files) to _rejected/ and record why."""
    src = directory / filename
    dest_dir = directory / REJECTED_DIR
    dest_dir.mkdir(exist_ok=True)
    for path in [src] + sidecars(src):
        shutil.move(str(path), str(dest_dir / path.name))
    reasons = read_json(dest_dir / REASONS, {})
    reasons[filename] = {"by": by, "reason": reason, "confidence": confidence,
                         "at": datetime.now().isoformat(timespec="seconds")}
    write_json(dest_dir / REASONS, reasons)


def restore_image(directory: Path, filename: str) -> None:
    """Move an image back from _rejected/."""
    rejected = directory / REJECTED_DIR
    src = rejected / filename
    for path in [src] + sidecars(src):
        shutil.move(str(path), str(directory / path.name))
    reasons = read_json(rejected / REASONS, {})
    reasons.pop(filename, None)
    write_json(rejected / REASONS, reasons)


def caption_of(image: Path) -> str:
    """Read the caption saved next to an image (txt, or the caption/prompt field of a json)."""
    txt = image.with_suffix(".txt")
    if txt.exists():
        return txt.read_text(encoding="utf-8").strip()
    data = read_json(image.with_suffix(".json"), None)
    if isinstance(data, dict):
        return data.get("caption") or data.get("prompt") or ""
    return ""


def write_caption(image: Path, fmt: str, caption: str, negative: str = "", tags: Optional[list] = None) -> Path:
    if fmt == "text":
        out = image.with_suffix(".txt")
        out.write_text(caption.strip() + "\n", encoding="utf-8")
        return out
    out = image.with_suffix(".json")
    existing = read_json(out, {})
    data = existing if isinstance(existing, dict) else {}
    data.update({"image": image.name, "timestamp": datetime.now().isoformat(timespec="seconds")})
    if fmt == "pairs":
        data.update({"prompt": caption, "negative_prompt": negative})
    else:
        data.update({"caption": caption, "tags": tags or []})
    write_json(out, data)
    return out


def dataset_summary(directory: Path) -> Dict[str, Any]:
    images = list_images(directory)
    rejected = list_images(directory / REJECTED_DIR)
    captioned = sum(1 for p in images if sidecars(p))
    manifest = read_json(directory / MANIFEST, {})
    return {
        "images": len(images),
        "rejected": len(rejected),
        "captioned": captioned,
        "profile": manifest.get("profile", {}),
        "feed_complete": manifest.get("feed_complete", False),
        "updated_at": manifest.get("updated_at", ""),
    }


# ---------------------------------------------------------------------- #
# Run context
# ---------------------------------------------------------------------- #

class RunContext:
    """What the pipeline needs from its caller: a log, a cancel flag, a progress hook."""

    def __init__(self, log: Callable[[str], None] = print,
                 cancel: Optional[threading.Event] = None,
                 progress: Callable[[Dict[str, Any]], None] = lambda _p: None):
        self.log = log
        self.cancel = cancel or threading.Event()
        self.progress = progress

    def stopped(self) -> bool:
        return self.cancel.is_set()

    def check(self) -> None:
        if self.cancel.is_set():
            raise Cancelled()


# ---------------------------------------------------------------------- #
# Steps
# ---------------------------------------------------------------------- #

def _download_one(session: requests.Session, ref: MediaRef, directory: Path) -> str:
    target = directory / ref.filename
    if target.exists() or (directory / REJECTED_DIR / ref.filename).exists():
        return "exists"
    response = session.get(ref.url, timeout=30)
    response.raise_for_status()
    tmp = target.with_suffix(".part")
    tmp.write_bytes(response.content)
    try:
        with Image.open(tmp) as img:
            img.verify()
    except Exception:
        tmp.unlink(missing_ok=True)
        raise ValueError("not a valid image")
    os.replace(tmp, target)
    return "new"


def download(refs: List[MediaRef], directory: Path, ctx: RunContext, workers: int = 4) -> Dict[str, List[str]]:
    """Download images in parallel. Returns {"new": [...], "exists": [...], "failed": [...]} filenames."""
    directory.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": DEFAULT_USER_AGENT, "Referer": "https://www.instagram.com/"})
    result: Dict[str, List[str]] = {"new": [], "exists": [], "failed": []}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_download_one, session, ref, directory): ref for ref in refs}
        for done, future in enumerate(as_completed(futures), 1):
            ref = futures[future]
            if ctx.stopped():
                for f in futures:
                    f.cancel()
                raise Cancelled()
            try:
                result[future.result()].append(ref.filename)
            except Exception as e:
                result["failed"].append(ref.filename)
                ctx.log(f"  ⚠ {ref.filename}: {e}")
            ctx.progress({"stage": "download", "done": done, "total": len(refs)})
    return result


def deduplicate(directory: Path, new_files: Iterable[str], ctx: RunContext) -> List[str]:
    """Move exact duplicates to _rejected/, keeping the copy that was already there."""
    new_files = set(new_files)
    moved = []
    groups = ImageDeduplicator().find_duplicates(str(directory))
    for files in groups.values():
        # Keep an older file over a new one, then by name
        ordered = sorted((Path(f).name for f in files), key=lambda n: (n in new_files, n))
        keep, dupes = ordered[0], ordered[1:]
        for name in dupes:
            reject_image(directory, name, f"duplicato di {keep}", "duplicate")
            moved.append(name)
    if moved:
        ctx.log(f"  {len(moved)} duplicati spostati in {REJECTED_DIR}/")
    return moved


def make_visual_ai(settings: Dict[str, Any]) -> VisualAI:
    engine, host, model = engine_endpoint(settings)
    return VisualAI(host=host, model=model, engine=engine, timeout=settings["ai_timeout"],
                    system_prompt=settings["system_prompt"], api_key=engine_api_key(settings))


def filter_images(ai: VisualAI, directory: Path, files: List[str], settings: Dict[str, Any],
                  ctx: RunContext) -> List[str]:
    rejected = []
    for i, name in enumerate(files, 1):
        ctx.check()
        path = directory / name
        if not path.exists():
            continue
        result = ai.filter_image(str(path), settings["filter_prompt"])
        if not result.success:
            ctx.log(f"  ⚠ {name}: {result.error}")
        elif result.filtered and result.confidence >= settings["min_confidence"]:
            reject_image(directory, name, result.reason or "scartata dal filtro", "filter", result.confidence)
            rejected.append(name)
            ctx.log(f"  ✗ {name} ({result.confidence:.2f}): {result.reason}")
        ctx.progress({"stage": "filter", "done": i, "total": len(files)})
    return rejected


def optimize_images(directory: Path, files: List[str], settings: Dict[str, Any], ctx: RunContext) -> int:
    optimizer = ImageOptimizer(target_size=settings["target_size"], quality=settings["image_quality"])
    count = 0
    for i, name in enumerate(files, 1):
        ctx.check()
        path = directory / name
        if path.exists() and optimizer.optimize_image(str(path)).success:
            count += 1
        ctx.progress({"stage": "optimize", "done": i, "total": len(files)})
    return count


def caption_images(ai: VisualAI, directory: Path, files: List[str], settings: Dict[str, Any],
                   media: Dict[str, Dict[str, Any]], ctx: RunContext) -> Dict[str, int]:
    fmt = settings["caption_format"]
    prefix = settings["caption_prefix"].strip()
    stats = {"done": 0, "failed": 0, "skipped": 0}
    for i, name in enumerate(files, 1):
        ctx.check()
        path = directory / name
        if not path.exists():
            continue
        if sidecars(path) and not settings["overwrite_captions"]:
            stats["skipped"] += 1
            continue
        context = (media.get(name) or {}).get("caption", "") if settings["use_ig_caption"] else ""
        result = ai.generate_caption(str(path), include_negative=fmt == "pairs",
                                     user_prompt=settings["caption_prompt"], context=context,
                                     negative_prompt=settings["negative_prompt"])
        if result.success:
            caption = f"{prefix} {result.caption}".strip() if prefix else result.caption
            write_caption(path, fmt, caption, result.negative_caption, result.tags)
            stats["done"] += 1
        else:
            stats["failed"] += 1
            ctx.log(f"  ⚠ {name}: {result.error}")
        ctx.progress({"stage": "caption", "done": i, "total": len(files)})
    return stats


# ---------------------------------------------------------------------- #
# Run
# ---------------------------------------------------------------------- #

def process_profile(scraper: InstagramScraper, username: str, settings: Dict[str, Any],
                    ai: Optional[VisualAI], ctx: RunContext) -> Dict[str, Any]:
    directory = profile_dir(settings["output_dir"], username)
    directory.mkdir(parents=True, exist_ok=True)
    manifest = read_json(directory / MANIFEST, {})
    known_media: Dict[str, Dict[str, Any]] = manifest.get("media", {})

    known_posts = None
    if settings["incremental"] and manifest.get("feed_complete"):
        known_posts = {m.get("parent_id") or m.get("id") for m in known_media.values() if m.get("source") == "post"}

    opts = ScrapeOptions(
        max_posts=settings["max_posts"],
        include_posts=settings["include_posts"],
        include_highlights=settings["include_highlights"],
        include_stories=settings["include_stories"],
        include_video_covers=settings["include_video_covers"],
        known_post_ids=known_posts,
    )

    ctx.progress({"stage": "scrape", "username": username, "done": 0, "total": 0})
    scraped = scraper.scrape(username, opts)
    ctx.check()
    refs: List[MediaRef] = scraped["media"]

    known_media.update({ref.filename: ref.to_dict() for ref in refs})
    write_json(directory / MANIFEST, {
        "profile": scraped["profile"],
        "feed_complete": manifest.get("feed_complete", False) or scraped["feed_complete"],
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "media": known_media,
    })

    ctx.log(f"📥 {len(refs)} immagini trovate, download in corso...")
    dl = download(refs, directory, ctx)
    ctx.log(f"  {len(dl['new'])} nuove, {len(dl['exists'])} già presenti, {len(dl['failed'])} fallite")

    duplicates: List[str] = []
    if settings["deduplicate"]:
        ctx.check()
        duplicates = deduplicate(directory, dl["new"], ctx)

    def in_scope() -> List[str]:
        if settings["process_scope"] == "all":
            return [p.name for p in list_images(directory)]
        return [n for n in dl["new"] if (directory / n).exists()]

    rejected: List[str] = []
    if settings["filter_enabled"] and ai:
        scope = in_scope()
        ctx.log(f"🔎 Filtro su {len(scope)} immagini")
        rejected = filter_images(ai, directory, scope, settings, ctx)

    optimized = 0
    if settings["optimize"]:
        scope = in_scope()
        ctx.log(f"🖼 Ottimizzazione di {len(scope)} immagini")
        optimized = optimize_images(directory, scope, settings, ctx)

    captions = {"done": 0, "failed": 0, "skipped": 0}
    if settings["captions_enabled"] and ai:
        scope = in_scope()
        ctx.log(f"📝 Caption per {len(scope)} immagini")
        captions = caption_images(ai, directory, scope, settings, known_media, ctx)

    summary = dataset_summary(directory)
    return {
        "username": username,
        "status": "ok" if not scraped["errors"] else "partial",
        "errors": scraped["errors"],
        "found": len(refs),
        "downloaded": len(dl["new"]),
        "existing": len(dl["exists"]),
        "failed": len(dl["failed"]),
        "duplicates": len(duplicates),
        "rejected": len(rejected),
        "optimized": optimized,
        "captioned": captions["done"],
        "caption_failed": captions["failed"],
        "kept": summary["images"],
        "dataset_captioned": summary["captioned"],
        "path": str(directory),
    }


def run(settings: Dict[str, Any], usernames: List[str], session_id: str,
        ctx: Optional[RunContext] = None) -> Dict[str, Any]:
    """
    Run the whole pipeline for a list of usernames with one browser.

    Returns {"status": "ok" | "partial" | "failed" | "cancelled", "profiles": [...], "error": str}.
    """
    ctx = ctx or RunContext()
    usernames = [u.strip().lstrip("@") for u in usernames if u and u.strip()]
    if not usernames:
        return {"status": "failed", "profiles": [], "error": "Nessun profilo da elaborare"}

    ai = None
    if settings["filter_enabled"] or settings["captions_enabled"]:
        ai = make_visual_ai(settings)
        ctx.log(f"🤖 Visual AI: {ai.engine} @ {ai.host} ({ai.model})")
        if not ai.check_availability():
            return {"status": "failed", "profiles": [],
                    "error": f"Visual AI '{ai.engine}' non raggiungibile su {ai.host}"}

    results: List[Dict[str, Any]] = []
    try:
        with InstagramClient(session_id,
                             rate_limit_delay=settings["rate_limit_delay"],
                             headless=settings["headless"],
                             log=ctx.log,
                             should_stop=ctx.stopped) as ig:
            ctx.log("🔐 Verifica sessione Instagram...")
            ig.check_session()
            scraper = InstagramScraper(ig, log=ctx.log, should_stop=ctx.stopped)

            for index, username in enumerate(usernames, 1):
                ctx.check()
                ctx.log(f"\n━━ [{index}/{len(usernames)}] @{username}")
                ctx.progress({"stage": "profile", "username": username, "index": index, "count": len(usernames)})
                try:
                    results.append(process_profile(scraper, username, settings, ai, ctx))
                except Cancelled:
                    raise
                except SessionInvalid:
                    raise
                except (InstagramError, Exception) as e:
                    ctx.log(f"✗ @{username}: {e}")
                    results.append({"username": username, "status": "failed", "errors": [str(e)]})
            ctx.log(f"\n✓ Fatto. Richieste a Instagram: {ig.requests_made}")
    except Cancelled:
        ctx.log("■ Interrotto")
        return {"status": "cancelled", "profiles": results, "error": ""}
    except SessionInvalid as e:
        ctx.log(f"✗ Sessione non valida: {e}")
        return {"status": "failed", "profiles": results, "error": f"Sessione non valida: {e}"}
    except Exception as e:
        ctx.log(f"✗ {type(e).__name__}: {e}")
        return {"status": "failed", "profiles": results, "error": str(e)}

    statuses = {r["status"] for r in results}
    status = "ok" if statuses == {"ok"} else ("failed" if statuses == {"failed"} else "partial")
    return {"status": status, "profiles": results, "error": ""}
