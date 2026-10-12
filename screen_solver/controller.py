from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .config import Settings

LOG = logging.getLogger(__name__)


def atomic_write(path: Path, content: str | bytes) -> None:
    """Keep the old result intact if a request or a disk write fails."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content.encode("utf-8") if isinstance(content, str) else content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def capture_desktop() -> bytes:
    from io import BytesIO
    from PIL import ImageGrab

    with ImageGrab.grab(all_screens=True) as screenshot:
        buffer = BytesIO()
        screenshot.save(buffer, format="PNG")
        return buffer.getvalue()


class Controller:
    """UI-thread state; only the Copilot request runs on a worker."""

    def __init__(self, settings: Settings, desktop, solver,
                 capture: Callable[[], bytes] = capture_desktop):
        self.settings = settings
        self.desktop = desktop
        self.solver = solver
        self.capture = capture
        self.revision = 0
        self.image: bytes | None = None
        self.solution: str | None = None
        self.future: Future | None = None
        self.job_revision = 0
        self.cancel = threading.Event()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="copilot")
        self.stopped = False
        self.stage = "waiting"
        self.settings.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.status("waiting", "Ready. Ctrl+Shift+Q captures all screens.")

    def status(self, stage: str, message: str) -> None:
        self.stage = stage
        LOG.info("%s: %s", stage, message)
        payload = {
            "stage": stage, "message": message, "pid": os.getpid(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "capture_revision": self.revision,
            "solution_ready": self.solution is not None,
            "solving": self.future is not None,
            "output_file": str(self.settings.output_file),
        }
        try:
            atomic_write(self.settings.runtime_dir / "status.json",
                         json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        except OSError:
            LOG.exception("Cannot write status.json")

    def handle(self, action: str) -> None:
        if self.stopped:
            return
        try:
            if action == "capture":
                image = self.capture()
                atomic_write(self.settings.runtime_dir / "latest.png", image)
                self.image = image
                self.revision += 1
                self.solution = None
                if self.future is not None:
                    self.cancel.set()
                self.status("captured", "Screenshot saved. Ctrl+Shift+E sends it to Copilot.")
            elif action == "solve":
                self.tick()
                if self.image is None:
                    self.status("waiting", "No screenshot. Press Ctrl+Shift+Q first.")
                elif self.future is not None:
                    self.status(self.stage, "A request is still running or stopping. Press E again shortly.")
                else:
                    self.solution = None
                    self.cancel = threading.Event()
                    self.job_revision = self.revision
                    # Immutable bytes prevent Q from changing an in-flight attachment.
                    self.future = self.executor.submit(self._solve, self.image, self.cancel)
                    self.status("solving", "Waiting for Copilot...")
            elif action == "paste":
                self.tick()
                if self.solution is None:
                    self.status(self.stage, "No solution for the current screenshot yet.")
                    return
                self.desktop.copy_text(self.solution)
                self.desktop.paste(click_at_pointer=self.settings.click_at_pointer)
                self.status("solution_ready", "Solution pasted.")
            elif action == "exit":
                self.close()
        except Exception as exc:
            LOG.exception("Action %s failed", action)
            self.status("error", f"{type(exc).__name__}: {exc}")

    def _solve(self, image: bytes, cancel: threading.Event) -> str:
        with tempfile.TemporaryDirectory(prefix="request-", dir=self.settings.runtime_dir) as directory:
            folder = Path(directory)
            attachment = folder / "screenshot.png"
            attachment.write_bytes(image)
            return self.solver.solve(attachment, folder, cancel)

    def tick(self) -> None:
        if self.stopped or self.future is None or not self.future.done():
            return
        future = self.future
        self.future = None
        if self.job_revision != self.revision:
            # A newer capture always wins, even if the old request just completed.
            try:
                future.result()
            except Exception:
                LOG.info("Previous capture request stopped or failed.")
            self.status("captured", "New screenshot ready. Press Ctrl+Shift+E.")
            return
        try:
            result = future.result()
            atomic_write(self.settings.output_file, result)
            self.solution = result
            self.desktop.copy_text(result)
            self.status("solution_ready", "a.txt saved and copied. Ctrl+Shift+O pastes the solution.")
        except Exception as exc:
            LOG.exception("Saving/copying solution failed")
            self.status("error", f"{type(exc).__name__}: {exc}")

    def close(self) -> None:
        if self.stopped:
            return
        self.stopped = True
        self.cancel.set()
        self.executor.shutdown(wait=True, cancel_futures=True)
        self.future = None
        self.solution = None
        self.status("stopped", "Stopped.")
