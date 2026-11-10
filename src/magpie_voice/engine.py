"""Runs NeMo-Speech.cpp's local HTTP server and talks to it."""

from __future__ import annotations

import os
import subprocess
import threading
import time

import httpx

from . import config


class Engine:
    def __init__(self, port: int = config.ENGINE_PORT) -> None:
        self.port = port
        self.base = f"http://127.0.0.1:{port}"
        self._proc: subprocess.Popen | None = None
        self._log = None
        self._start_lock = threading.Lock()

    # -- lifecycle -------------------------------------------------------
    def available(self) -> bool:
        return config.ENGINE_EXE.exists()

    def _healthy(self) -> bool:
        try:
            return httpx.get(f"{self.base}/health", timeout=2).status_code == 200
        except httpx.HTTPError:
            return False

    def start(self, timeout: float = 120) -> None:
        with self._start_lock:
            if self._healthy():
                return
            if not config.ENGINE_EXE.exists():
                raise RuntimeError(
                    f"Speech engine not found at {config.ENGINE_EXE}. Run scripts/setup.ps1 first."
                )
            env = dict(os.environ, NEMO_SPEECH_MODEL_DIR=str(config.MODELS_DIR))
            if self._log is None:
                self._log = open(config.log_dir() / "engine.log", "ab")
            self._proc = subprocess.Popen(
                [str(config.ENGINE_EXE), "serve", "--host", "127.0.0.1", "--port", str(self.port),
                 "--no-ui", "--tts-model", "magpie"],
                env=env, stdin=subprocess.DEVNULL, stdout=self._log, stderr=self._log,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if self._proc.poll() is not None:
                    raise RuntimeError(
                        f"Speech engine exited with code {self._proc.returncode}; "
                        f"see {config.log_dir() / 'engine.log'}"
                    )
                if self._healthy():
                    return
                time.sleep(0.25)
            self.stop()
            raise RuntimeError("Speech engine did not become ready in time")

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None

    # -- calls -----------------------------------------------------------
    def _request(self, method: str, path: str, **kw) -> httpx.Response:
        try:
            return httpx.request(method, f"{self.base}{path}", timeout=120, **kw)
        except httpx.TransportError:
            self.start()
            return httpx.request(method, f"{self.base}{path}", timeout=120, **kw)

    def synthesize(self, text: str, voice: str, language: str) -> bytes:
        r = self._request("POST", "/v1/audio/speech", json={
            "input": text, "voice": voice, "language": language, "response_format": "pcm",
        })
        if r.status_code == 400:
            raise ValueError(r.text)
        r.raise_for_status()
        return r.content

    def voices(self) -> dict:
        r = self._request("GET", "/v1/models")
        r.raise_for_status()
        for m in r.json().get("data", []):
            if m.get("capability") == "speech":
                return {"voices": m.get("voices", []), "languages": m.get("languages", [])}
        return {"voices": [], "languages": []}
