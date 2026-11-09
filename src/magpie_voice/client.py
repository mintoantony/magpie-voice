"""Talks to the speaker daemon, starting it when needed."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

import httpx

from . import config


def _spawn_daemon(port: int) -> None:
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = str(pythonw if pythonw.exists() else sys.executable)
    flags = (getattr(subprocess, "DETACHED_PROCESS", 0)
             | getattr(subprocess, "CREATE_NO_WINDOW", 0)
             | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    subprocess.Popen([exe, "-m", "magpie_voice", "daemon", "--port", str(port)],
                     cwd=str(config.ROOT), creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Client:
    def __init__(self, port: int = config.DAEMON_PORT,
                 spawn: Callable[[], None] | None = None) -> None:
        self.port = port
        self.base = f"http://127.0.0.1:{port}"
        self._spawn = spawn or (lambda: _spawn_daemon(port))

    def _alive(self) -> bool:
        try:
            return httpx.get(f"{self.base}/status", timeout=2).status_code == 200
        except httpx.HTTPError:
            return False

    def ensure_daemon(self, timeout: float = 60) -> None:
        if self._alive():
            return
        self._spawn()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._alive():
                return
            time.sleep(0.25)
        raise RuntimeError("Magpie Voice daemon did not start; see "
                           f"{config.log_dir() / 'daemon.log'}")

    def _call(self, method: str, path: str, body: dict | None = None, timeout: float = 30) -> dict:
        self.ensure_daemon()
        r = httpx.request(method, f"{self.base}{path}", json=body, timeout=timeout)
        if r.status_code == 400:
            raise ValueError(r.json().get("error", r.text))
        if r.status_code != 200:
            try:
                msg = r.json().get("error", r.text)
            except ValueError:
                msg = r.text
            raise RuntimeError(msg)
        return r.json()

    def speak(self, text: str, voice: str | None = None, language: str | None = None) -> dict:
        return self._call("POST", "/speak", {"text": text, "voice": voice, "language": language})

    def stop(self) -> dict:
        return self._call("POST", "/stop", {})

    def save(self, text: str, path: str | None = None, voice: str | None = None,
             language: str | None = None, format: str | None = None,
             overwrite: bool = False, clean: bool = True) -> dict:
        return self._call("POST", "/save", {
            "text": text, "path": path, "voice": voice, "language": language,
            "format": format, "overwrite": overwrite, "clean": clean}, timeout=1800)

    def voices(self) -> dict:
        return self._call("GET", "/voices")

    def status(self) -> dict:
        return self._call("GET", "/status")

    def wait_done(self, request_id: str, timeout: float | None = None) -> None:
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            try:
                s = self.status()
            except (httpx.HTTPError, RuntimeError):
                s = None  # daemon went away; status() restarts it next time round
            if s is not None and s["playing"] != request_id and request_id not in s["queued"]:
                return
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError(f"request {request_id} still playing")
            time.sleep(0.3)


_default = Client()
speak = _default.speak
stop = _default.stop
save = _default.save
voices = _default.voices
status = _default.status
wait_done = _default.wait_done
ensure_daemon = _default.ensure_daemon
