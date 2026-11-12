"""
Background job runner: one worker thread, runs execute one at a time (never two scrapers
hitting Instagram at once), each with its own log file and cancel flag.
"""

import io
import queue
import sys
import threading
import time
import traceback
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from .. import pipeline
from ..store import Store, now


class _ThreadRoutedStdout(io.TextIOBase):
    """
    sys.stdout replacement that sends writes from registered threads to their run's log
    and everything else to the real stdout. Lets the pipeline's inner modules keep `print`.
    """

    def __init__(self, original):
        self.original = original
        self.targets: Dict[int, Callable[[str], None]] = {}

    def write(self, text: str) -> int:
        target = self.targets.get(threading.get_ident())
        if target:
            target(text)
            return len(text)
        try:
            self.original.write(text)
        except UnicodeEncodeError:
            # A console or file that is not UTF-8 (cp1252 on Windows) must never break a request
            enc = getattr(self.original, "encoding", None) or "ascii"
            self.original.write(text.encode(enc, "replace").decode(enc, "replace"))
        return len(text)

    def flush(self) -> None:
        self.original.flush()

    @property
    def encoding(self):  # rich and others ask for it
        return getattr(self.original, "encoding", "utf-8")

    def isatty(self) -> bool:
        return False


class Runner:
    def __init__(self, store: Store):
        self.store = store
        self.queue: "queue.Queue[str]" = queue.Queue()
        self.cancels: Dict[str, threading.Event] = {}
        self.current: Optional[str] = None
        self.progress: Dict[str, Dict[str, Any]] = {}
        self._stdout = self._install_stdout()
        self._recover()
        self._thread = threading.Thread(target=self._worker, name="crawler-runner", daemon=True)
        self._thread.start()

    @staticmethod
    def _install_stdout() -> _ThreadRoutedStdout:
        """(Re)install the routing stdout; something else may have replaced sys.stdout since."""
        if not isinstance(sys.stdout, _ThreadRoutedStdout):
            sys.stdout = _ThreadRoutedStdout(sys.stdout)
        return sys.stdout

    def _recover(self) -> None:
        """Runs left 'running' or 'queued' by a previous process were interrupted."""
        for run in self.store.runs(limit=10_000):
            if run["status"] in ("running", "queued"):
                run.update({"status": "interrupted", "finished_at": run.get("finished_at") or now(),
                            "error": "Il server è stato chiuso durante l'esecuzione"})
                self.store.save_run(run)

    # ------------------------------------------------------------------ #

    def submit(self, job: Dict[str, Any]) -> Dict[str, Any]:
        effective = self.store.effective(job)
        settings = {k: v["value"] for k, v in effective.items()}
        if not job.get("usernames"):
            raise ValueError("Il job non ha profili")
        # Fail now, not in the background, if the account is missing
        if not self.store.session_for(settings["account"]):
            raise ValueError("Nessuna sessione Instagram: aggiungi un account o INSTAGRAM_SESSION_ID nel .env")
        run = self.store.create_run(job, settings)
        run["sources"] = {k: v["source"] for k, v in effective.items()}
        self.store.save_run(run)
        self.cancels[run["id"]] = threading.Event()
        self.queue.put(run["id"])
        return run

    def cancel(self, run_id: str) -> bool:
        run = self.store.run(run_id)
        if run["status"] == "queued":
            run.update({"status": "cancelled", "finished_at": now()})
            self.store.save_run(run)
        event = self.cancels.get(run_id)
        if event:
            event.set()
            return True
        return False

    def live_progress(self, run_id: str) -> Dict[str, Any]:
        return self.progress.get(run_id, {})

    def queued_ids(self):
        return list(self.queue.queue)

    # ------------------------------------------------------------------ #

    def _worker(self) -> None:
        while True:
            run_id = self.queue.get()
            try:
                self._execute(run_id)
            except Exception:  # never let the worker die
                self._stdout.original.write(traceback.format_exc())
            finally:
                self.current = None
                self.cancels.pop(run_id, None)
                self.progress.pop(run_id, None)

    def _execute(self, run_id: str) -> None:
        run = self.store.run(run_id)
        if run["status"] != "queued":
            return
        cancel = self.cancels.setdefault(run_id, threading.Event())
        self.current = run_id
        run.update({"status": "running", "started_at": now()})
        self.store.save_run(run)

        def log(message: str) -> None:
            self.store.append_log(run_id, message if message.endswith("\n") else message + "\n")

        last_save = [0.0]

        def progress(update: Dict[str, Any]) -> None:
            state = self.progress.setdefault(run_id, {})
            state.update(update)
            if time.monotonic() - last_save[0] > 2:
                last_save[0] = time.monotonic()
                run["progress"] = dict(state)
                self.store.save_run(run)

        self._stdout = self._install_stdout()
        self._stdout.targets[threading.get_ident()] = lambda text: self.store.append_log(run_id, text)
        log(f"▶ {run['job_name']} · {len(run['usernames'])} profili · {datetime.now():%d/%m/%Y %H:%M}")
        try:
            session_id = self.store.session_for(run["settings"]["account"])
            ctx = pipeline.RunContext(log=log, cancel=cancel, progress=progress)
            result = pipeline.run(run["settings"], run["usernames"], session_id, ctx)
            run.update({"status": result["status"], "result": result["profiles"], "error": result["error"]})
        except Exception as e:
            log(traceback.format_exc())
            run.update({"status": "failed", "error": f"{type(e).__name__}: {e}"})
        finally:
            self._stdout.targets.pop(threading.get_ident(), None)
            run["progress"] = self.progress.get(run_id, {})
            run["finished_at"] = now()
            self.store.save_run(run)
