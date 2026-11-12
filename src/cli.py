"""
CLI module - Command-line interface for the application.

    instagram-crawler <username> [options]      one profile
    instagram-crawler --batch users.txt         several profiles, one browser
    instagram-crawler --job "My job"            a job saved from the GUI
    instagram-crawler gui                       open the web GUI

Settings are resolved as in the GUI: command-line flags -> job -> global (GUI) -> .env -> default.
"""

import argparse
import sys
from typing import Any, Dict, List, Optional

from . import pipeline
from .settings import SECRET_KEYS, resolve, values
from .store import Store, parse_usernames


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="InstagramProfileCrawler - Create datasets from Instagram profiles",
        epilog="Run 'instagram-crawler gui' for the web interface.",
    )
    parser.add_argument("username", nargs="?", help="Instagram username to scrape")

    parser.add_argument("--batch", type=str, help="File with usernames (one per line)")
    parser.add_argument("--job", type=str, help="Run a job saved in the GUI (name or id)")
    parser.add_argument("--account", type=str, help="Account id saved in the GUI (default: .env session)")
    parser.add_argument("--data-dir", default="data", help="GUI data folder (jobs, accounts, global settings)")

    parser.add_argument("--max-posts", type=int, help="Maximum number of posts (0 = all)")
    parser.add_argument("--output", "-o", type=str, help="Output directory (one subfolder per profile)")
    parser.add_argument("--stories", action="store_true", help="Also download current (24h) stories")
    parser.add_argument("--no-highlights", action="store_true", help="Skip story highlights")
    parser.add_argument("--full", action="store_true", help="Ignore incremental mode and page through every post")
    parser.add_argument("--all", action="store_true", dest="process_all",
                        help="Filter/optimize/caption the whole dataset, not only new images")

    parser.add_argument("--optimize", action="store_true", help="Optimize images for LoRA training")
    parser.add_argument("--deduplicate", action="store_true", help="Move duplicate images to _rejected/")
    parser.add_argument("--generate-captions", action="store_true", help="Generate captions using Visual AI")
    parser.add_argument("--caption-format", choices=["text", "json", "pairs"], help="Format for caption output")
    parser.add_argument("--engine", choices=["ollama", "llama.cpp", "strata"],
                        help="Visual AI engine (overrides VISUAL_AI_TYPE from .env)")
    parser.add_argument("--filter", action="store_true", help="Filter images using Visual AI")
    parser.add_argument("--show-browser", action="store_true", help="Show the Chromium window")

    parser.add_argument("--verbose", "-v", action="store_true", help="Print the resolved settings")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    return parser


def cli_overrides(args: argparse.Namespace) -> Dict[str, Any]:
    """Only flags the user actually passed become overrides."""
    o: Dict[str, Any] = {}
    if args.max_posts is not None:
        o["max_posts"] = args.max_posts
    if args.output:
        o["output_dir"] = args.output
    if args.stories:
        o["include_stories"] = True
    if args.no_highlights:
        o["include_highlights"] = False
    if args.full:
        o["incremental"] = False
    if args.process_all:
        o["process_scope"] = "all"
    if args.optimize:
        o["optimize"] = True
    if args.deduplicate:
        o["deduplicate"] = True
    if args.generate_captions:
        o["captions_enabled"] = True
    if args.caption_format:
        o["caption_format"] = args.caption_format
    if args.engine:
        o["engine"] = args.engine
    if args.filter:
        o["filter_enabled"] = True
    if args.show_browser:
        o["headless"] = False
    if args.account:
        o["account"] = args.account
    return o


def print_summary(result: Dict[str, Any]) -> None:
    for p in result["profiles"]:
        if p.get("status") == "failed":
            print(f"\n✗ @{p['username']}: {'; '.join(p.get('errors', []))}")
            continue
        print(f"\n✓ @{p['username']} → {p['path']}")
        print(f"  Found {p['found']} · new {p['downloaded']} · existing {p['existing']} · failed {p['failed']}")
        print(f"  Duplicates {p['duplicates']} · rejected {p['rejected']} · captions {p['captioned']}")
        print(f"  In dataset: {p['kept']} images ({p['dataset_captioned']} captioned)")
        for err in p.get("errors", []):
            print(f"  ⚠ {err}")
    if result.get("error"):
        print(f"\n✗ {result['error']}")


def main(argv: Optional[List[str]] = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    from .utils import safe_console
    safe_console()
    if argv[:1] == ["gui"]:
        from .web.app import main as gui_main
        gui_main(argv[1:])
        return

    parser = create_parser()
    args = parser.parse_args(argv)
    store = Store(args.data_dir)

    job_overrides: Dict[str, Any] = {}
    if args.job:
        try:
            job = store.find_job(args.job)
        except KeyError:
            parser.error(f"job '{args.job}' not found in {args.data_dir}/jobs")
        usernames = job["usernames"]
        job_overrides = job.get("overrides", {})
    elif args.batch:
        with open(args.batch, encoding="utf-8") as f:
            usernames = parse_usernames(f.read())
    elif args.username:
        usernames = parse_usernames(args.username)
    else:
        parser.print_help()
        return

    try:
        resolved = resolve(store.global_overrides(), {**job_overrides, **cli_overrides(args)})
        settings = values(resolved)
        session_id = store.session_for(settings["account"])
    except ValueError as e:
        parser.error(str(e))

    if not session_id:
        parser.error("no Instagram session: set INSTAGRAM_SESSION_ID in .env or add an account in the GUI")

    if args.verbose:
        for key, item in resolved.items():
            if key in SECRET_KEYS:
                print(f"  {key} = {'<set>' if item['value'] else '<not set>'}  ({item['source']})")
            elif key not in ("system_prompt", "caption_prompt", "negative_prompt"):
                print(f"  {key} = {item['value']!r}  ({item['source']})")

    log = (lambda _m: None) if args.quiet else print
    result = pipeline.run(settings, usernames, session_id, pipeline.RunContext(log=log))
    print_summary(result)
    if result["status"] in ("failed", "cancelled"):
        sys.exit(1)


if __name__ == "__main__":
    main()
