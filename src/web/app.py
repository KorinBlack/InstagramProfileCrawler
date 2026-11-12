"""
Web GUI for InstagramProfileCrawler.

    python -m src.web            # http://127.0.0.1:8765
    instagram-crawler gui

Listens on 127.0.0.1 only by default: the GUI holds Instagram session cookies.
"""

import argparse
import re
import tempfile
import threading
import webbrowser
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from .. import __version__, pipeline
from ..instagram.auth import check_session, mask_secret
from ..settings import (FIELDS, GROUPS, engine_endpoint, mask_resolved, mask_values, resolve,
                        unmask_overrides, values)
from ..store import ENV_ACCOUNT_ID, Store, parse_usernames
from .runner import Runner

STATIC_DIR = Path(__file__).parent / "static"
FILENAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,200}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")


def create_app(data_dir: str = "data", allowed_hosts: Optional[set] = None) -> FastAPI:
    store = Store(data_dir)
    runner = Runner(store)
    app = FastAPI(title="InstagramProfileCrawler", docs_url=None, redoc_url=None)
    app.state.store = store
    app.state.runner = runner
    hosts = allowed_hosts or {"127.0.0.1", "localhost", "testserver"}

    # ------------------------------------------------------------------ #
    # Local-only protections: DNS rebinding (Host header) and cross-site
    # requests (custom header forces a CORS preflight that we never allow).
    # ------------------------------------------------------------------ #
    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
        if host not in hosts:
            return JSONResponse({"detail": "Host non consentito"}, status_code=403)
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.url.path.startswith("/api/"):
            if request.headers.get("x-requested-with") != "crawler-gui":
                return JSONResponse({"detail": "Richiesta non consentita"}, status_code=403)
        return await call_next(request)

    def not_found(what: str):
        raise HTTPException(404, f"{what} non trovato")

    def get_job(job_id: str) -> Dict[str, Any]:
        try:
            return store.job(job_id)
        except KeyError:
            not_found("Job")

    def public_account(a: Dict[str, Any]) -> Dict[str, Any]:
        account_ref = "" if a["id"] == ENV_ACCOUNT_ID else a["id"]
        jobs = sum(1 for j in store.jobs() if j.get("overrides", {}).get("account") == account_ref
                   and "account" in j.get("overrides", {})) if account_ref else 0
        return {
            "id": a["id"], "label": a.get("label", ""), "session": mask_secret(a.get("session_id", "")),
            "readonly": a.get("readonly", False), "valid": a.get("valid"), "checked_at": a.get("checked_at", ""),
            "user_id": a.get("user_id", ""), "used_by_jobs": jobs,
            "used_globally": bool(account_ref) and store.global_overrides().get("account") == account_ref,
        }

    # API keys never leave the server in clear: every response goes through these
    def public_job(job: Dict[str, Any]) -> Dict[str, Any]:
        return {**job, "overrides": mask_values(job.get("overrides", {}))}

    def public_run(run: Dict[str, Any]) -> Dict[str, Any]:
        return {**run, "settings": mask_values(run.get("settings", {}))}

    def job_summary(job: Dict[str, Any]) -> Dict[str, Any]:
        runs = store.runs(job_id=job["id"], limit=1)
        settings = values(store.effective(job))
        totals = {"images": 0, "rejected": 0, "captioned": 0}
        for username in job.get("usernames", []):
            s = pipeline.dataset_summary(pipeline.profile_dir(settings["output_dir"], username))
            for k in totals:
                totals[k] += s[k]
        return {**public_job(job), "last_run": public_run(runs[0]) if runs else None, "dataset": totals,
                "override_count": len(job.get("overrides", {}))}

    def dataset_dir(job_id: str, username: str) -> Path:
        job = get_job(job_id)
        if not USERNAME_RE.match(username):
            not_found("Profilo")
        settings = values(store.effective(job))
        return pipeline.profile_dir(settings["output_dir"], username)

    def image_path(directory: Path, view: str, name: str) -> Path:
        if not FILENAME_RE.match(name) or view not in ("kept", "rejected"):
            not_found("File")
        base = directory if view == "kept" else directory / pipeline.REJECTED_DIR
        path = (base / name).resolve()
        if base.resolve() not in path.parents or not path.is_file():
            not_found("File")
        return path

    # ------------------------------------------------------------------ #
    # Meta
    # ------------------------------------------------------------------ #

    @app.get("/api/meta")
    def meta():
        current = runner.current
        return {
            "version": __version__,
            "data_dir": str(store.root.resolve()),
            "current_run": public_run(store.run(current)) if current else None,
            "queued": len(runner.queued_ids()),
        }

    @app.get("/api/ui")
    def get_ui():
        return store.ui_state()

    @app.put("/api/ui")
    def put_ui(payload: Dict[str, Any] = Body(...)):
        return store.set_ui_state(payload)

    @app.get("/api/schema")
    def schema():
        return {"groups": [{"id": g, "label": label} for g, label in GROUPS],
                "fields": [f.to_dict() for f in FIELDS]}

    # ------------------------------------------------------------------ #
    # Global settings
    # ------------------------------------------------------------------ #

    @app.get("/api/settings")
    def get_settings():
        # effective: what a job inherits; base: what the global level inherits (.env / default)
        return {"overrides": mask_values(store.global_overrides()),
                "effective": mask_resolved(store.effective()), "base": mask_resolved(resolve())}

    @app.put("/api/settings")
    def put_settings(payload: Dict[str, Any] = Body(...)):
        overrides = unmask_overrides(payload.get("overrides", {}), store.global_overrides(), values(resolve()))
        try:
            store.set_global_overrides(overrides)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return get_settings()

    @app.post("/api/engine/check")
    def engine_check(payload: Dict[str, Any] = Body(default={})):
        # Checks the values on screen, including unsaved edits, at the job or the global level
        if payload.get("job_id"):
            job = get_job(payload["job_id"])
            edits = unmask_overrides(payload.get("overrides", {}), job.get("overrides", {}),
                                     values(store.effective()))
            overrides = {**job.get("overrides", {}), **edits}
        else:
            overrides = unmask_overrides(payload.get("overrides", {}), store.global_overrides(), values(resolve()))
        try:
            settings = values(resolve(store.global_overrides(), overrides))
        except ValueError as e:
            raise HTTPException(400, str(e))
        engine, host, model = engine_endpoint(settings)
        ai = pipeline.make_visual_ai(settings)
        ok = ai.check_availability()
        return {"ok": ok, "engine": engine, "host": host, "model": model}

    # ------------------------------------------------------------------ #
    # Accounts
    # ------------------------------------------------------------------ #

    @app.get("/api/accounts")
    def list_accounts():
        return [public_account(a) for a in store.accounts()]

    @app.post("/api/accounts")
    def create_account(payload: Dict[str, Any] = Body(...)):
        try:
            return public_account(store.save_account(payload))
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.put("/api/accounts/{account_id}")
    def update_account(account_id: str, payload: Dict[str, Any] = Body(...)):
        if account_id == ENV_ACCOUNT_ID:
            raise HTTPException(400, "La sessione del .env si modifica nel file .env")
        try:
            return public_account(store.save_account(payload, account_id))
        except KeyError:
            not_found("Account")
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.delete("/api/accounts/{account_id}")
    def delete_account(account_id: str):
        store.delete_account(account_id)
        return {"ok": True}

    @app.post("/api/accounts/{account_id}/check")
    def check_account(account_id: str):
        account = store.account(account_id)
        if not account:
            not_found("Account")
        if runner.current:
            raise HTTPException(409, "Un'esecuzione è in corso: riprova quando finisce")
        result = check_session(account["session_id"])
        if account_id != ENV_ACCOUNT_ID:
            store.mark_account(account_id, result["valid"], result["user_id"])
        return result

    # ------------------------------------------------------------------ #
    # Jobs
    # ------------------------------------------------------------------ #

    @app.get("/api/jobs")
    def list_jobs():
        return [job_summary(j) for j in store.jobs()]

    def with_real_secrets(payload: Dict[str, Any], stored: Dict[str, Any]) -> Dict[str, Any]:
        if "overrides" not in payload:
            return payload
        # A job inherits from the global level, so that is where an inherited key comes from
        return {**payload, "overrides": unmask_overrides(payload["overrides"], stored, values(store.effective()))}

    @app.post("/api/jobs")
    def create_job(payload: Dict[str, Any] = Body(...)):
        try:
            return public_job(store.save_job(with_real_secrets(payload, {})))
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.get("/api/jobs/{job_id}")
    def read_job(job_id: str):
        job = get_job(job_id)
        return {**job_summary(job), "effective": mask_resolved(store.effective(job))}

    @app.put("/api/jobs/{job_id}")
    def update_job(job_id: str, payload: Dict[str, Any] = Body(...)):
        current = get_job(job_id)
        try:
            job = store.save_job(with_real_secrets(payload, current.get("overrides", {})), job_id)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {**job_summary(job), "effective": mask_resolved(store.effective(job))}

    @app.post("/api/jobs/{job_id}/duplicate")
    def duplicate_job(job_id: str):
        get_job(job_id)
        return public_job(store.duplicate_job(job_id))

    @app.delete("/api/jobs/{job_id}")
    def delete_job(job_id: str):
        get_job(job_id)
        store.delete_job(job_id)
        return {"ok": True}

    @app.post("/api/jobs/{job_id}/run")
    def run_job(job_id: str):
        job = get_job(job_id)
        try:
            return public_run(runner.submit(job))
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/usernames/parse")
    def parse(payload: Dict[str, Any] = Body(...)):
        return {"usernames": parse_usernames(payload.get("text", ""))}

    # ------------------------------------------------------------------ #
    # Runs
    # ------------------------------------------------------------------ #

    @app.get("/api/runs")
    def list_runs(job_id: Optional[str] = None, limit: int = 50):
        return [public_run(r) for r in store.runs(job_id=job_id, limit=limit)]

    @app.get("/api/runs/{run_id}")
    def read_run(run_id: str, offset: int = 0):
        try:
            run = store.run(run_id)
        except KeyError:
            not_found("Esecuzione")
        live = runner.live_progress(run_id)
        if live:
            run["progress"] = live
        return {**public_run(run), "log": store.read_log(run_id, offset)}

    @app.post("/api/runs/{run_id}/cancel")
    def cancel_run(run_id: str):
        try:
            runner.cancel(run_id)
        except KeyError:
            not_found("Esecuzione")
        return {"ok": True}

    # ------------------------------------------------------------------ #
    # Datasets
    # ------------------------------------------------------------------ #

    @app.get("/api/jobs/{job_id}/datasets")
    def job_datasets(job_id: str):
        job = get_job(job_id)
        settings = values(store.effective(job))
        return [{"username": u, **pipeline.dataset_summary(pipeline.profile_dir(settings["output_dir"], u))}
                for u in job.get("usernames", [])]

    @app.get("/api/datasets/{job_id}/{username}")
    def dataset_images(job_id: str, username: str, view: str = "kept"):
        directory = dataset_dir(job_id, username)
        media = pipeline.read_json(directory / pipeline.MANIFEST, {}).get("media", {})
        reasons = pipeline.read_json(directory / pipeline.REJECTED_DIR / pipeline.REASONS, {})
        base = directory if view == "kept" else directory / pipeline.REJECTED_DIR
        items = []
        for path in pipeline.list_images(base):
            m = media.get(path.name, {})
            items.append({
                "name": path.name, "caption": pipeline.caption_of(path),
                "has_caption": bool(pipeline.sidecars(path)),
                "source": m.get("source", ""), "ig_caption": m.get("caption", ""),
                "taken_at": m.get("taken_at", 0), "code": m.get("code", ""),
                "width": m.get("width", 0), "height": m.get("height", 0),
                "reason": reasons.get(path.name),
            })
        items.sort(key=lambda i: i["taken_at"] or 0, reverse=True)
        return {"summary": pipeline.dataset_summary(directory), "items": items, "path": str(directory)}

    @app.get("/api/datasets/{job_id}/{username}/file/{view}/{name}")
    def dataset_file(job_id: str, username: str, view: str, name: str):
        return FileResponse(image_path(dataset_dir(job_id, username), view, name),
                            headers={"Cache-Control": "private, max-age=3600"})

    @app.put("/api/datasets/{job_id}/{username}/caption/{name}")
    def save_caption(job_id: str, username: str, name: str, payload: Dict[str, Any] = Body(...)):
        directory = dataset_dir(job_id, username)
        path = image_path(directory, "kept", name)
        settings = values(store.effective(get_job(job_id)))
        fmt = "pairs" if path.with_suffix(".json").exists() and \
            "prompt" in pipeline.read_json(path.with_suffix(".json"), {}) else None
        if fmt is None:
            fmt = "json" if path.with_suffix(".json").exists() and not path.with_suffix(".txt").exists() \
                else ("text" if path.with_suffix(".txt").exists() else settings["caption_format"])
        caption = str(payload.get("caption", ""))
        if fmt == "pairs":
            data = pipeline.read_json(path.with_suffix(".json"), {})
            pipeline.write_caption(path, "pairs", caption, data.get("negative_prompt", ""))
        else:
            pipeline.write_caption(path, fmt, caption)
        return {"ok": True, "format": fmt}

    @app.post("/api/datasets/{job_id}/{username}/reject/{name}")
    def reject(job_id: str, username: str, name: str):
        directory = dataset_dir(job_id, username)
        image_path(directory, "kept", name)
        pipeline.reject_image(directory, name, "scartata a mano", "manual")
        return {"ok": True}

    @app.post("/api/datasets/{job_id}/{username}/restore/{name}")
    def restore(job_id: str, username: str, name: str):
        directory = dataset_dir(job_id, username)
        image_path(directory, "rejected", name)
        pipeline.restore_image(directory, name)
        return {"ok": True}

    @app.get("/api/datasets/{job_id}/{username}/export")
    def export(job_id: str, username: str):
        directory = dataset_dir(job_id, username)
        images = pipeline.list_images(directory)
        if not images:
            not_found("Dataset")
        tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        tmp.close()
        with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_STORED) as zf:
            for image in images:
                zf.write(image, f"{username}/{image.name}")
                for side in pipeline.sidecars(image):
                    zf.write(side, f"{username}/{side.name}")
        return FileResponse(tmp.name, filename=f"{username}-dataset.zip", media_type="application/zip",
                            background=BackgroundTask(lambda: Path(tmp.name).unlink(missing_ok=True)))

    # ------------------------------------------------------------------ #
    # Frontend
    # ------------------------------------------------------------------ #

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="InstagramProfileCrawler web GUI")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Indirizzo di ascolto (default: solo questo computer)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", default="data", help="Cartella per job, account ed esecuzioni")
    parser.add_argument("--no-browser", action="store_true", help="Non aprire il browser")
    args = parser.parse_args(argv)

    import uvicorn

    from ..utils import safe_console
    safe_console()

    hosts = {"127.0.0.1", "localhost"}
    if args.host not in ("127.0.0.1", "localhost"):
        print("⚠ La GUI contiene le sessioni Instagram: esporla in rete permette a chiunque la "
              "raggiunga di usarle. Usala solo su una rete fidata.")
        hosts.add(args.host)

    app = create_app(args.data_dir, allowed_hosts=hosts)
    url = f"http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{args.port}/"
    print(f"InstagramProfileCrawler GUI su {url}")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
