"""
Tests for the scraper logic, the pipeline, the store and the web API.
No network and no browser: Instagram and the model are faked.
"""

import io
import time

import pytest
from PIL import Image

from src import pipeline, settings as settings_mod
from src.instagram.client import InstagramError
from src.instagram.scraper import InstagramScraper, ScrapeOptions, extract_media
from src.store import Store, parse_usernames


@pytest.fixture(autouse=True)
def no_dotenv(monkeypatch):
    """Ignore the developer's real .env in every test."""
    monkeypatch.setattr(settings_mod, "load_dotenv", lambda *a, **k: None)
    import src.store as store_mod
    monkeypatch.setattr(store_mod, "load_dotenv", lambda *a, **k: None)
    for f in settings_mod.FIELDS:
        if f.env:
            monkeypatch.delenv(f.env, raising=False)
    monkeypatch.delenv("INSTAGRAM_SESSION_ID", raising=False)


def jpeg_bytes(color="red", size=(64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="JPEG")
    return buf.getvalue()


def image_item(pk, w=1080, url=None, caption="", media_type=1):
    return {
        "pk": pk, "media_type": media_type, "taken_at": 1700000000 + int(pk), "code": f"C{pk}",
        "caption": {"text": caption} if caption else None,
        "image_versions2": {"candidates": [
            {"url": url or f"https://cdn/{pk}_small.jpg", "width": 320, "height": 400},
            {"url": url or f"https://cdn/{pk}.jpg", "width": w, "height": int(w * 1.25)},
        ]},
    }


# ---------------------------------------------------------------------- #
# Settings
# ---------------------------------------------------------------------- #

class TestSettings:
    def test_precedence(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_DELAY", "3")
        monkeypatch.setenv("VISUAL_AI_TYPE", "strata")
        r = settings_mod.resolve({"rate_limit_delay": 2, "max_posts": 50}, {"max_posts": 10})
        assert r["max_posts"] == {"value": 10, "source": "job"}
        assert r["rate_limit_delay"] == {"value": 2.0, "source": "global"}
        assert r["engine"] == {"value": "strata", "source": "env"}
        assert r["deduplicate"] == {"value": True, "source": "default"}

    def test_invalid_layer_value_falls_through(self, monkeypatch):
        monkeypatch.setenv("VISUAL_AI_TYPE", "nonsense")
        r = settings_mod.resolve({}, {"engine": "also-bad"})
        assert r["engine"] == {"value": "ollama", "source": "default"}

    def test_clean_overrides(self):
        cleaned = settings_mod.clean_overrides({"max_posts": "12", "unknown": 1, "headless": "false"})
        assert cleaned == {"max_posts": 12, "headless": False}
        with pytest.raises(ValueError):
            settings_mod.clean_overrides({"min_confidence": 3})

    def test_engine_endpoint(self):
        s = settings_mod.values(settings_mod.resolve({}, {"engine": "strata"}))
        assert settings_mod.engine_endpoint(s) == ("strata", "http://127.0.0.1:8080", "qwen3.8-flash-next")


# ---------------------------------------------------------------------- #
# Scraper
# ---------------------------------------------------------------------- #

class TestExtractMedia:
    def test_best_candidate_and_caption(self):
        refs = extract_media(image_item(1, caption="ciao"), "post")
        assert len(refs) == 1
        assert refs[0].url == "https://cdn/1.jpg" and refs[0].width == 1080
        assert refs[0].caption == "ciao" and refs[0].filename == "post_1.jpg"

    def test_carousel_children_share_caption(self):
        item = {"pk": 9, "media_type": 8, "code": "X", "caption": {"text": "c"}, "taken_at": 5,
                "carousel_media": [image_item(91), image_item(92), {**image_item(93), "media_type": 2}]}
        refs = extract_media(item, "post")
        assert [r.id for r in refs] == ["91", "92"]
        assert all(r.caption == "c" and r.parent_id == "9" and r.code == "X" for r in refs)
        assert len(extract_media(item, "post", include_video_covers=True)) == 3


class FakeClient:
    """Answers api_get from a dict of path-prefix -> response (or exception)."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def api_get(self, path):
        self.calls.append(path)
        for prefix, response in self.routes:
            if path.startswith(prefix):
                if isinstance(response, Exception):
                    raise response
                return response(path) if callable(response) else response
        raise InstagramError(f"no route for {path}")

    def page_html(self, url):
        self.calls.append(url)
        return '<a href="/stories/highlights/555/">x</a><a href="/stories/highlights/555/">x</a>'


PROFILE = {"data": {"user": {"id": "42", "username": "nasa", "edge_owner_to_timeline_media": {"count": 5}}}}


def feed_routes():
    page1 = {"items": [image_item(1), image_item(2)], "more_available": True, "next_max_id": "c1"}
    page2 = {"items": [image_item(3)], "more_available": False}
    return [
        ("/api/v1/users/web_profile_info/", PROFILE),
        ("/api/v1/feed/user/nasa/username/", page1),
        ("/api/v1/feed/user/42/?count=33&max_id=c1", page2),
    ]


class TestScraper:
    def test_paginates_to_the_end(self):
        client = FakeClient(feed_routes())
        out = InstagramScraper(client, log=lambda m: None).scrape(
            "nasa", ScrapeOptions(include_highlights=False))
        assert [r.id for r in out["media"]] == ["1", "2", "3"]
        assert out["feed_complete"] is True

    def test_max_posts(self):
        client = FakeClient(feed_routes())
        out = InstagramScraper(client, log=lambda m: None).scrape(
            "nasa", ScrapeOptions(max_posts=2, include_highlights=False))
        assert len(out["media"]) == 2
        assert not any("max_id" in c for c in client.calls)

    def test_incremental_stops_on_known_page(self):
        client = FakeClient(feed_routes())
        out = InstagramScraper(client, log=lambda m: None).scrape(
            "nasa", ScrapeOptions(include_highlights=False, known_post_ids={"1", "2"}))
        assert len(out["media"]) == 2  # page 1 only
        assert not any("max_id" in c for c in client.calls)

    def test_highlights_api_batched(self):
        routes = feed_routes() + [
            ("/api/v1/highlights/42/highlights_tray/", {"tray": [{"id": "highlight:7"}, {"id": "highlight:8"}]}),
            ("/api/v1/feed/reels_media/", {"reels": {"highlight:7": {"items": [image_item(70)]},
                                                     "highlight:8": {"items": [image_item(80)]}}}),
        ]
        client = FakeClient(routes)
        out = InstagramScraper(client, log=lambda m: None).scrape("nasa", ScrapeOptions(include_posts=False))
        assert sorted(r.filename for r in out["media"]) == ["highlight_70.jpg", "highlight_80.jpg"]
        reels_calls = [c for c in client.calls if "reels_media" in c]
        assert len(reels_calls) == 1 and "highlight:7" in reels_calls[0] and "highlight:8" in reels_calls[0]

    def test_highlight_tray_falls_back_to_profile_html(self):
        routes = feed_routes() + [
            ("/api/v1/highlights/", InstagramError("HTTP 400")),
            ("/api/v1/feed/reels_media/", {"reels": {"highlight:555": {"items": [image_item(5)]}}}),
        ]
        out = InstagramScraper(FakeClient(routes), log=lambda m: None).scrape(
            "nasa", ScrapeOptions(include_posts=False))
        assert [r.filename for r in out["media"]] == ["highlight_5.jpg"]

    def test_failing_section_does_not_lose_the_others(self):
        routes = [
            ("/api/v1/users/web_profile_info/", PROFILE),
            ("/api/v1/feed/user/", InstagramError("HTTP 500 after 3 retries")),
            ("/api/v1/highlights/42/", {"tray": [{"id": "highlight:7"}]}),
            ("/api/v1/feed/reels_media/", {"reels": {"highlight:7": {"items": [image_item(70)]}}}),
        ]
        out = InstagramScraper(FakeClient(routes), log=lambda m: None).scrape("nasa", ScrapeOptions())
        assert [r.filename for r in out["media"]] == ["highlight_70.jpg"]
        assert out["errors"] and out["errors"][0].startswith("posts:")


# ---------------------------------------------------------------------- #
# Pipeline
# ---------------------------------------------------------------------- #

class FakeScraper:
    def __init__(self, refs, feed_complete=True):
        self.refs = refs
        self.feed_complete = feed_complete
        self.opts = None

    def scrape(self, username, opts):
        self.opts = opts
        return {"profile": {"username": username}, "media": self.refs,
                "feed_complete": self.feed_complete, "errors": []}


class FakeAI:
    engine, host, model = "strata", "http://x", "m"

    def __init__(self, reject=()):
        self.reject = set(reject)

    def filter_image(self, path, prompt):
        from src.filtering.visual_ai import VisualAIResult
        name = path.replace("\\", "/").rsplit("/", 1)[-1]
        return VisualAIResult(success=True, filtered=name in self.reject, confidence=0.9, reason="sfocata")

    def generate_caption(self, path, include_negative=False, user_prompt="", context="", negative_prompt=""):
        from src.filtering.visual_ai import VisualAIResult
        return VisualAIResult(success=True, caption=f"a photo{' about ' + context if context else ''}",
                              negative_caption="blurry" if include_negative else "")


@pytest.fixture
def fake_cdn(monkeypatch):
    """requests.Session.get returns a JPEG whose colour comes from the URL ('dup' -> same bytes)."""
    colors = iter(["red", "green", "blue", "yellow", "white", "black", "orange", "purple"])
    cache = {}

    class Resp:
        def __init__(self, content):
            self.content = content

        def raise_for_status(self):
            pass

    def get(self, url, timeout=None):
        key = "dup" if "dup" in url else url
        if key not in cache:
            cache[key] = jpeg_bytes(next(colors))
        return Resp(cache[key])

    monkeypatch.setattr(pipeline.requests.Session, "get", get)


def refs_for(*ids, source="post"):
    from src.instagram.scraper import MediaRef
    return [MediaRef(id=str(i), url=f"https://cdn/{i}.jpg", source=source, caption=f"cap {i}") for i in ids]


def run_settings(tmp_path, **overrides):
    s = settings_mod.values(settings_mod.resolve({}, {"output_dir": str(tmp_path), **overrides}))
    return s


class TestPipeline:
    def test_download_dedupe_filter_caption(self, tmp_path, fake_cdn):
        from src.instagram.scraper import MediaRef
        refs = refs_for(1, 2) + [MediaRef(id="3", url="https://cdn/dup/a.jpg", source="post"),
                                 MediaRef(id="4", url="https://cdn/dup/b.jpg", source="post")]
        s = run_settings(tmp_path, filter_enabled=True, captions_enabled=True, caption_prefix="ohwx,",
                         use_ig_caption=True)
        ctx = pipeline.RunContext(log=lambda m: None)
        out = pipeline.process_profile(FakeScraper(refs), "nasa", s, FakeAI(reject={"post_2.jpg"}), ctx)

        d = tmp_path / "nasa"
        assert out["downloaded"] == 4 and out["duplicates"] == 1 and out["rejected"] == 1
        assert sorted(p.name for p in pipeline.list_images(d)) == ["post_1.jpg", "post_3.jpg"]
        assert (d / "post_1.txt").read_text(encoding="utf-8").strip() == "ohwx, a photo about cap 1"
        reasons = pipeline.read_json(d / "_rejected" / "reasons.json", {})
        assert reasons["post_2.jpg"]["by"] == "filter" and reasons["post_4.jpg"]["by"] == "duplicate"
        assert pipeline.read_json(d / "manifest.json", {})["feed_complete"] is True

    def test_second_pass_skips_existing_and_uses_incremental(self, tmp_path, fake_cdn):
        s = run_settings(tmp_path)
        ctx = pipeline.RunContext(log=lambda m: None)
        pipeline.process_profile(FakeScraper(refs_for(1, 2)), "nasa", s, None, ctx)
        scraper = FakeScraper(refs_for(1, 2, 3))
        out = pipeline.process_profile(scraper, "nasa", s, None, ctx)
        assert out["downloaded"] == 1 and out["existing"] == 2
        assert scraper.opts.known_post_ids == {"1", "2"}

    def test_low_confidence_is_kept(self, tmp_path, fake_cdn):
        s = run_settings(tmp_path, filter_enabled=True, min_confidence=0.95)
        out = pipeline.process_profile(FakeScraper(refs_for(1)), "nasa", s, FakeAI(reject={"post_1.jpg"}),
                                       pipeline.RunContext(log=lambda m: None))
        assert out["rejected"] == 0

    def test_reject_and_restore_move_captions(self, tmp_path):
        d = tmp_path / "p"
        d.mkdir()
        Image.new("RGB", (8, 8)).save(d / "a.jpg")
        (d / "a.txt").write_text("cap", encoding="utf-8")
        pipeline.reject_image(d, "a.jpg", "brutta", "manual")
        assert not (d / "a.jpg").exists() and (d / "_rejected" / "a.txt").exists()
        pipeline.restore_image(d, "a.jpg")
        assert pipeline.caption_of(d / "a.jpg") == "cap"
        assert pipeline.read_json(d / "_rejected" / "reasons.json", {}) == {}

    def test_cancel(self, tmp_path, fake_cdn):
        ctx = pipeline.RunContext(log=lambda m: None)
        ctx.cancel.set()
        with pytest.raises(pipeline.Cancelled):
            pipeline.process_profile(FakeScraper(refs_for(1, 2)), "nasa", run_settings(tmp_path), None, ctx)


# ---------------------------------------------------------------------- #
# Store
# ---------------------------------------------------------------------- #

class TestStore:
    def test_parse_usernames(self):
        text = "@nasa\nhttps://www.instagram.com/natgeo/?hl=it, bad!name, nasa ; esa"
        assert parse_usernames(text) == ["nasa", "natgeo", "esa"]

    def test_jobs_and_effective(self, tmp_path):
        store = Store(str(tmp_path))
        store.set_global_overrides({"max_posts": 100})
        job = store.save_job({"name": "J", "usernames": "a b", "overrides": {"max_posts": 5, "nope": 1}})
        assert job["overrides"] == {"max_posts": 5}
        assert store.effective(job)["max_posts"] == {"value": 5, "source": "job"}
        assert store.effective()["max_posts"] == {"value": 100, "source": "global"}
        assert store.duplicate_job(job["id"])["name"] == "J (copia)"
        assert store.find_job("j")["id"] in {j["id"] for j in store.jobs()}

    def test_accounts(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INSTAGRAM_SESSION_ID", "envsession123456")
        store = Store(str(tmp_path))
        acc = store.save_account({"label": "Lavoro", "session_id": "sessionid=abcdef1234567890;"})
        assert acc["session_id"] == "abcdef1234567890"
        assert [a["id"] for a in store.accounts()] == ["env", acc["id"]]
        assert store.session_for("") == "envsession123456"
        assert store.session_for(acc["id"]) == "abcdef1234567890"
        with pytest.raises(ValueError):
            store.session_for("missing")


# ---------------------------------------------------------------------- #
# Web API
# ---------------------------------------------------------------------- #

@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from src.web.app import create_app
    monkeypatch.setenv("INSTAGRAM_SESSION_ID", "envsession123456")
    app = create_app(str(tmp_path / "data"))
    c = TestClient(app)
    c.headers.update({"x-requested-with": "crawler-gui"})
    return c


class TestWeb:
    def test_mutations_need_the_gui_header_and_a_local_host(self, client):
        from fastapi.testclient import TestClient
        bare = TestClient(client.app)
        assert bare.post("/api/jobs", json={"name": "x"}).status_code == 403
        assert client.get("/api/jobs", headers={"host": "evil.example"}).status_code == 403
        assert client.post("/api/jobs", json={"name": "x"}).status_code == 200

    def test_job_crud_and_sources(self, client, tmp_path):
        client.put("/api/settings", json={"overrides": {"max_posts": 30}})
        job = client.post("/api/jobs", json={"name": "Alpi", "usernames": "@a\nb",
                                             "overrides": {"engine": "strata"}}).json()
        detail = client.get(f"/api/jobs/{job['id']}").json()
        assert detail["usernames"] == ["a", "b"]
        assert detail["effective"]["engine"]["source"] == "job"
        assert detail["effective"]["max_posts"] == {"value": 30, "source": "global"}
        assert client.put(f"/api/jobs/{job['id']}", json={"overrides": {"min_confidence": 7}}).status_code == 400
        assert client.delete(f"/api/jobs/{job['id']}").json() == {"ok": True}
        assert client.get(f"/api/jobs/{job['id']}").status_code == 404

    def test_accounts_never_leak_the_session(self, client):
        created = client.post("/api/accounts", json={"label": "B", "session_id": "verysecretsession9999"}).json()
        listed = client.get("/api/accounts").json()
        body = str(listed)
        assert "verysecretsession9999" not in body and "envsession123456" not in body
        assert created["session"] == "very…9999"

    def test_dataset_endpoints(self, client, tmp_path):
        out = tmp_path / "ds"
        job = client.post("/api/jobs", json={"name": "D", "usernames": "nasa",
                                             "overrides": {"output_dir": str(out)}}).json()
        d = out / "nasa"
        d.mkdir(parents=True)
        Image.new("RGB", (8, 8)).save(d / "post_1.jpg")
        base = f"/api/datasets/{job['id']}/nasa"
        items = client.get(base).json()["items"]
        assert [i["name"] for i in items] == ["post_1.jpg"]
        assert client.put(f"{base}/caption/post_1.jpg", json={"caption": "hello"}).json()["format"] == "text"
        assert (d / "post_1.txt").read_text(encoding="utf-8").strip() == "hello"
        assert client.get(f"{base}/file/kept/post_1.jpg").status_code == 200
        assert client.get(f"{base}/file/kept/..%2F..%2Fsecret.txt").status_code == 404
        assert client.post(f"{base}/reject/post_1.jpg").json() == {"ok": True}
        assert client.get(f"{base}?view=rejected").json()["items"][0]["reason"]["by"] == "manual"
        assert client.post(f"{base}/restore/post_1.jpg").json() == {"ok": True}
        export = client.get(f"{base}/export")
        assert export.status_code == 200 and export.content[:2] == b"PK"

    def test_run_job_end_to_end(self, client, monkeypatch):
        captured = {}

        def fake_run(settings, usernames, session_id, ctx):
            captured.update(settings=settings, usernames=usernames, session=session_id)
            ctx.log("✓ fake run")
            print("printed by an inner module")
            return {"status": "ok", "profiles": [{"username": "a", "status": "ok", "kept": 3}], "error": ""}

        monkeypatch.setattr(pipeline, "run", fake_run)
        job = client.post("/api/jobs", json={"name": "R", "usernames": "a",
                                             "overrides": {"max_posts": 7}}).json()
        run = client.post(f"/api/jobs/{job['id']}/run").json()
        for _ in range(50):
            data = client.get(f"/api/runs/{run['id']}").json()
            if data["status"] not in ("queued", "running"):
                break
            time.sleep(0.05)
        assert data["status"] == "ok"
        assert "fake run" in data["log"]["text"] and "printed by an inner module" in data["log"]["text"]
        assert captured["settings"]["max_posts"] == 7 and captured["session"] == "envsession123456"
        assert data["sources"]["max_posts"] == "job"

    def test_run_without_profiles_is_refused(self, client):
        job = client.post("/api/jobs", json={"name": "Empty"}).json()
        assert client.post(f"/api/jobs/{job['id']}/run").status_code == 400

    def test_stdout_proxy_survives_non_utf8_console(self):
        """Regression: '⚠' printed on a cp1252 console made /api/engine/check fail with 500."""
        import io as _io
        from src.web.runner import _ThreadRoutedStdout
        raw = _io.BytesIO()
        console = _io.TextIOWrapper(raw, encoding="cp1252", newline="\n")
        proxy = _ThreadRoutedStdout(console)
        assert proxy.write("⚠ AI service unavailable\n") == len("⚠ AI service unavailable\n")
        console.flush()
        assert raw.getvalue() == b"? AI service unavailable\n"

    def test_tour_state_persists(self, client):
        assert client.get("/api/ui").json() == {"tour_seen": False}
        assert client.put("/api/ui", json={"tour_seen": True, "junk": 1}).json() == {"tour_seen": True}
        from src.web.app import create_app
        from fastapi.testclient import TestClient
        again = TestClient(create_app(str(client.app.state.store.root)))
        assert again.get("/api/ui").json() == {"tour_seen": True}

    def test_frontend_is_served(self, client):
        assert "Profile Crawler" in client.get("/").text
        assert client.get("/static/app.js").status_code == 200


# ---------------------------------------------------------------------- #
# Engine API keys
# ---------------------------------------------------------------------- #

class TestApiKeys:
    def test_bearer_header_is_sent(self, monkeypatch, tmp_path):
        from src.filtering.visual_ai import VisualAI
        seen = {}

        class R:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": '{"keep": true, "confidence": 1}'}}]}

        def post(url, json=None, headers=None, timeout=None):
            seen["post"] = headers
            return R()

        def get(url, headers=None, timeout=None):
            seen["get"] = headers
            return R()

        monkeypatch.setattr("src.filtering.visual_ai.requests.post", post)
        monkeypatch.setattr("src.filtering.visual_ai.requests.get", get)
        img = tmp_path / "a.jpg"
        Image.new("RGB", (8, 8)).save(img)

        ai = VisualAI(host="http://x", engine="strata", api_key="sk-123")
        assert ai.check_availability() and ai.filter_image(str(img), "").success
        assert seen["get"] == seen["post"] == {"Authorization": "Bearer sk-123"}
        assert VisualAI(host="http://x", engine="llama.cpp").headers == {}

    def test_pipeline_uses_the_selected_engine_key(self, monkeypatch):
        monkeypatch.setenv("VISUAL_AI_STRATA_API_KEY", "strata-key")
        s = settings_mod.values(settings_mod.resolve({"llama_api_key": "llama-key"}, {"engine": "strata"}))
        assert pipeline.make_visual_ai(s).api_key == "strata-key"
        s["engine"] = "llama.cpp"
        assert pipeline.make_visual_ai(s).api_key == "llama-key"

    def test_unmask(self):
        masked = settings_mod.mask_secret_value("sk-abcdefgh1234")
        assert masked == "__secret__:…1234"
        out = settings_mod.unmask_overrides({"strata_api_key": masked, "max_posts": 3},
                                            stored={"strata_api_key": "sk-abcdefgh1234"}, inherited={})
        assert out == {"strata_api_key": "sk-abcdefgh1234", "max_posts": 3}
        # customizing an inherited key without typing keeps the inherited value
        assert settings_mod.unmask_overrides({"strata_api_key": masked}, {}, {"strata_api_key": "glob"}) \
            == {"strata_api_key": "glob"}

    def test_web_never_returns_keys_and_keeps_them_on_save(self, client, monkeypatch):
        client.put("/api/settings", json={"overrides": {"strata_api_key": "global-secret-key-0001"}})
        body = client.get("/api/settings").json()
        assert "global-secret-key-0001" not in str(body)
        assert body["overrides"]["strata_api_key"] == "__secret__:…0001"

        # The page sends the masked value back unchanged -> the real key is kept
        client.put("/api/settings", json={"overrides": body["overrides"]})
        from src.store import Store
        store: Store = client.app.state.store
        assert store.global_overrides()["strata_api_key"] == "global-secret-key-0001"

        # A job that "customizes" the inherited key without typing gets the real global key
        job = client.post("/api/jobs", json={"name": "K", "usernames": "a",
                                             "overrides": {"strata_api_key": "__secret__:…0001"}}).json()
        assert store.job(job["id"])["overrides"]["strata_api_key"] == "global-secret-key-0001"
        assert "global-secret-key-0001" not in str(client.get(f"/api/jobs/{job['id']}").json())

        # A new key typed in the job replaces it; the run snapshot is masked too
        client.put(f"/api/jobs/{job['id']}", json={"overrides": {"strata_api_key": "job-key-9999"}})
        assert store.job(job["id"])["overrides"]["strata_api_key"] == "job-key-9999"
        monkeypatch.setattr(pipeline, "run", lambda *a, **k: {"status": "ok", "profiles": [], "error": ""})
        run = client.post(f"/api/jobs/{job['id']}/run").json()
        assert run["settings"]["strata_api_key"] == "__secret__:…9999"
        assert "job-key-9999" not in str(client.get("/api/runs").json())

    def test_engine_check_uses_the_key(self, client, monkeypatch):
        captured = {}

        def fake_make(settings):
            captured["key"] = settings["strata_api_key"]

            class AI:
                def check_availability(self):
                    return True
            return AI()

        monkeypatch.setattr(pipeline, "make_visual_ai", fake_make)
        client.put("/api/settings", json={"overrides": {"engine": "strata", "strata_api_key": "saved-key-7777"}})
        masked = client.get("/api/settings").json()["overrides"]
        assert client.post("/api/engine/check", json={"overrides": masked}).json()["ok"]
        assert captured["key"] == "saved-key-7777"
        client.post("/api/engine/check", json={"overrides": {**masked, "strata_api_key": "typed-key"}})
        assert captured["key"] == "typed-key"
