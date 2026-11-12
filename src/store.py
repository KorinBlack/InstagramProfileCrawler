"""
Local storage for the GUI and the CLI: global settings, Instagram accounts, jobs and runs.

Plain JSON files under data/ (git-ignored), so they are easy to read, back up and diff:

    data/global.json          global setting overrides
    data/accounts.json        saved Instagram sessions (secrets: never sent back to the browser)
    data/jobs/<id>.json       a job: profiles + its own overrides
    data/runs/<id>.json       one execution of a job: status, summary
    data/runs/<id>.log        its log
"""

import os
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from .pipeline import read_json, write_json
from .settings import clean_overrides, resolve

ENV_ACCOUNT_ID = "env"


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex[:10]


_ID_RE = re.compile(r"^[a-z0-9]{1,32}$")


def safe_id(value: str) -> str:
    if not _ID_RE.match(value or ""):
        raise KeyError(value)
    return value


def parse_usernames(raw: Any) -> List[str]:
    """Accept a list or free text (one per line, commas, spaces, @ or profile URLs)."""
    if isinstance(raw, list):
        items = raw
    else:
        items = re.split(r"[\s,;]+", str(raw or ""))
    names = []
    for item in items:
        item = str(item).strip()
        match = re.search(r"instagram\.com/([^/?#]+)", item)
        if match:
            item = match.group(1)
        item = item.lstrip("@").strip("/")
        if re.fullmatch(r"[A-Za-z0-9._]{1,30}", item) and item not in names:
            names.append(item)
    return names


class Store:
    def __init__(self, data_dir: str = "data"):
        self.root = Path(data_dir)
        self.jobs_dir = self.root / "jobs"
        self.runs_dir = self.root / "runs"
        for d in (self.jobs_dir, self.runs_dir):
            d.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # Global settings
    # ------------------------------------------------------------------ #

    def global_overrides(self) -> Dict[str, Any]:
        return read_json(self.root / "global.json", {})

    def set_global_overrides(self, overrides: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = clean_overrides(overrides)
        with self._lock:
            write_json(self.root / "global.json", cleaned)
        return cleaned

    # ------------------------------------------------------------------ #
    # GUI state (e.g. whether the first-start tour has been seen)
    # ------------------------------------------------------------------ #

    UI_KEYS = {"tour_seen": bool}

    def ui_state(self) -> Dict[str, Any]:
        state = read_json(self.root / "ui.json", {})
        return {key: kind(state.get(key, False)) for key, kind in self.UI_KEYS.items()}

    def set_ui_state(self, changes: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            state = self.ui_state()
            state.update({k: self.UI_KEYS[k](v) for k, v in (changes or {}).items() if k in self.UI_KEYS})
            write_json(self.root / "ui.json", state)
            return state

    # ------------------------------------------------------------------ #
    # Accounts
    # ------------------------------------------------------------------ #

    def _accounts(self) -> List[Dict[str, Any]]:
        return read_json(self.root / "accounts.json", [])

    def accounts(self) -> List[Dict[str, Any]]:
        """All accounts, including the implicit one from .env, with secrets included."""
        load_dotenv()
        env_session = os.getenv("INSTAGRAM_SESSION_ID", "")
        items = []
        if env_session:
            items.append({"id": ENV_ACCOUNT_ID, "label": "Sessione da .env", "session_id": env_session,
                          "readonly": True, "checked_at": "", "valid": None, "user_id": ""})
        items.extend(self._accounts())
        return items

    def account(self, account_id: str) -> Optional[Dict[str, Any]]:
        return next((a for a in self.accounts() if a["id"] == account_id), None)

    def save_account(self, data: Dict[str, Any], account_id: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            accounts = self._accounts()
            if account_id:
                account = next((a for a in accounts if a["id"] == account_id), None)
                if account is None:
                    raise KeyError(account_id)
            else:
                account = {"id": new_id(), "created_at": now(), "valid": None, "checked_at": "", "user_id": ""}
                accounts.append(account)
            if "label" in data:
                account["label"] = str(data["label"]).strip() or "Account"
            if data.get("session_id"):
                # A cookie pasted from the browser may be URL-encoded or include "sessionid="
                session = str(data["session_id"]).strip().removeprefix("sessionid=").strip(";")
                if session != account.get("session_id"):
                    account.update({"session_id": session, "valid": None, "checked_at": ""})
            if not account.get("session_id"):
                raise ValueError("Session ID mancante")
            write_json(self.root / "accounts.json", accounts)
            return account

    def mark_account(self, account_id: str, valid: bool, user_id: str = "") -> None:
        with self._lock:
            accounts = self._accounts()
            for a in accounts:
                if a["id"] == account_id:
                    a.update({"valid": valid, "checked_at": now(), "user_id": user_id or a.get("user_id", "")})
            write_json(self.root / "accounts.json", accounts)

    def delete_account(self, account_id: str) -> None:
        with self._lock:
            write_json(self.root / "accounts.json", [a for a in self._accounts() if a["id"] != account_id])

    def session_for(self, account_id: str) -> str:
        if account_id:
            account = self.account(account_id)
            if account is None:
                raise ValueError(f"Account '{account_id}' non trovato")
            return account["session_id"]
        load_dotenv()
        return os.getenv("INSTAGRAM_SESSION_ID", "")

    # ------------------------------------------------------------------ #
    # Jobs
    # ------------------------------------------------------------------ #

    def jobs(self) -> List[Dict[str, Any]]:
        jobs = [read_json(p, None) for p in self.jobs_dir.glob("*.json")]
        return sorted((j for j in jobs if j), key=lambda j: j.get("updated_at", ""), reverse=True)

    def job(self, job_id: str) -> Dict[str, Any]:
        job = read_json(self.jobs_dir / f"{safe_id(job_id)}.json", None)
        if job is None:
            raise KeyError(job_id)
        return job

    def find_job(self, name_or_id: str) -> Dict[str, Any]:
        for job in self.jobs():
            if job["id"] == name_or_id or job["name"].lower() == name_or_id.lower():
                return job
        raise KeyError(name_or_id)

    def save_job(self, data: Dict[str, Any], job_id: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            if job_id:
                job = self.job(job_id)
            else:
                job = {"id": new_id(), "created_at": now(), "overrides": {}, "usernames": [], "notes": ""}
            if "name" in data:
                job["name"] = str(data["name"]).strip() or "Job senza nome"
            if "usernames" in data:
                job["usernames"] = parse_usernames(data["usernames"])
            if "notes" in data:
                job["notes"] = str(data["notes"])
            if "overrides" in data:
                job["overrides"] = clean_overrides(data["overrides"])
            job.setdefault("name", "Job senza nome")
            job["updated_at"] = now()
            write_json(self.jobs_dir / f"{job['id']}.json", job)
            return job

    def duplicate_job(self, job_id: str) -> Dict[str, Any]:
        job = self.job(job_id)
        return self.save_job({"name": f"{job['name']} (copia)", "usernames": job["usernames"],
                              "notes": job.get("notes", ""), "overrides": job.get("overrides", {})})

    def delete_job(self, job_id: str) -> None:
        (self.jobs_dir / f"{safe_id(job_id)}.json").unlink(missing_ok=True)

    def effective(self, job: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
        return resolve(self.global_overrides(), (job or {}).get("overrides"))

    # ------------------------------------------------------------------ #
    # Runs
    # ------------------------------------------------------------------ #

    def create_run(self, job: Dict[str, Any], settings: Dict[str, Any]) -> Dict[str, Any]:
        run = {
            "id": new_id(), "job_id": job["id"], "job_name": job["name"],
            "usernames": job["usernames"], "status": "queued",
            "created_at": now(), "started_at": "", "finished_at": "",
            "settings": {k: v for k, v in settings.items() if k != "session_id"},
            "progress": {}, "result": None, "error": "",
        }
        self.save_run(run)
        return run

    def save_run(self, run: Dict[str, Any]) -> None:
        with self._lock:
            write_json(self.runs_dir / f"{run['id']}.json", run)

    def run(self, run_id: str) -> Dict[str, Any]:
        run = read_json(self.runs_dir / f"{safe_id(run_id)}.json", None)
        if run is None:
            raise KeyError(run_id)
        return run

    def runs(self, job_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        runs = [read_json(p, None) for p in self.runs_dir.glob("*.json")]
        runs = [r for r in runs if r and (job_id is None or r.get("job_id") == job_id)]
        runs.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return runs[:limit]

    def log_path(self, run_id: str) -> Path:
        return self.runs_dir / f"{safe_id(run_id)}.log"

    def append_log(self, run_id: str, text: str) -> None:
        with self._lock, open(self.log_path(run_id), "a", encoding="utf-8", newline="") as f:
            f.write(text)

    def read_log(self, run_id: str, offset: int = 0) -> Dict[str, Any]:
        path = self.log_path(run_id)
        if not path.exists():
            return {"text": "", "offset": 0}
        with open(path, "rb") as f:
            f.seek(offset)
            data = f.read()
        return {"text": data.decode("utf-8", errors="replace"), "offset": offset + len(data)}
