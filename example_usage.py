"""
Examples of using InstagramProfileCrawler from Python.

For everyday use the web GUI (`python -m src.web`) or the CLI (`python -m src.cli`)
is simpler; these show the building blocks underneath.
"""

from src import pipeline
from src.instagram import InstagramClient, InstagramScraper, ScrapeOptions, check_session
from src.settings import resolve, values
from src.store import Store


def example_full_pipeline(username: str = "example_username"):
    """Run the same pipeline as the GUI: download, deduplicate and caption one profile."""
    store = Store("data")
    settings = values(resolve(store.global_overrides(), {
        "max_posts": 20,
        "captions_enabled": True,
        "caption_format": "text",
        "caption_prefix": "ohwx,",
    }))
    session_id = store.session_for(settings["account"])
    result = pipeline.run(settings, [username], session_id)
    print(result["status"], result["profiles"])


def example_scrape_only(username: str = "example_username"):
    """List the images of a profile without downloading anything."""
    session_id = Store("data").session_for("")
    with InstagramClient(session_id, rate_limit_delay=1.5) as ig:
        ig.check_session()
        data = InstagramScraper(ig).scrape(username, ScrapeOptions(max_posts=12, include_highlights=False))
    for ref in data["media"]:
        print(ref.filename, ref.width, "x", ref.height, ref.caption[:40])


def example_caption_one_image(path: str):
    """Caption a single local image with the engine configured in .env / the GUI."""
    settings = values(resolve(Store("data").global_overrides()))
    ai = pipeline.make_visual_ai(settings)
    if not ai.check_availability():
        print(f"{ai.engine} is not reachable at {ai.host}")
        return
    result = ai.generate_caption(path, include_negative=False)
    print(result.caption if result.success else result.error)


def example_check_session():
    """Verify the session in .env."""
    print(check_session(Store("data").session_for("")))


if __name__ == "__main__":
    example_check_session()
