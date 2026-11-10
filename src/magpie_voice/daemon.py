"""The PC-wide speaker daemon: one engine, one read-aloud queue, one player."""

from __future__ import annotations

import json
import logging
import queue
import socket
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import audio, config, text

log = logging.getLogger("magpie_voice.daemon")

RUN_AHEAD = 3


@dataclass
class Request:
    id: str
    chunks: list[str]
    voice: str
    language: str
    audio: queue.Queue = field(default_factory=queue.Queue)
    cancelled: bool = False
    progress: int = 0


class _ExclusiveServer(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets a second process bind the same port;
    # the port must be exclusive so it can act as the one-daemon lock.
    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class Daemon:
    def __init__(self, engine, player, port: int = config.DAEMON_PORT,
                 idle_timeout: float = 1800, host: str = "127.0.0.1") -> None:
        self.engine = engine
        self.player = player
        self.idle_timeout = idle_timeout
        self._cond = threading.Condition()
        self._engine_lock = threading.Lock()
        self._play_queue: deque[Request] = deque()
        self._synth_queue: deque[Request] = deque()
        self._playing: Request | None = None
        self._done: deque[str] = deque(maxlen=50)
        self._errors: dict[str, str] = {}
        self._saving = 0
        self._last_activity = time.monotonic()
        self._running = True
        self.httpd = _ExclusiveServer((host, port), self._handler_class())  # raises OSError if taken
        self.port = self.httpd.server_address[1]

    # -- public operations ---------------------------------------------------
    def speak(self, body: dict) -> dict:
        voice = config.normalize_voice(body.get("voice"))
        language = config.normalize_language(body.get("language"))
        chunks = text.prepare(str(body.get("text", "")), language)
        available = getattr(self.engine, "available", None)
        if available is not None and not available():
            raise RuntimeError(
                f"Speech engine not found at {config.ENGINE_EXE}. Run scripts/setup.ps1 first.")
        req = Request(uuid.uuid4().hex[:8], chunks, voice, language)
        with self._cond:
            position = len(self._play_queue) + (1 if self._playing else 0)
            self._play_queue.append(req)
            self._synth_queue.append(req)
            self._touch()
            self._cond.notify_all()
        return {"id": req.id, "position": position, "chunks": len(chunks)}

    def stop(self) -> dict:
        with self._cond:
            victims = list(self._play_queue)
            if self._playing:
                victims.append(self._playing)
            for r in victims:
                r.cancelled = True
                r.audio.put(None)
            self._play_queue.clear()
            self._synth_queue.clear()
            self._touch()
            self._cond.notify_all()
        self.player.stop()
        return {"stopped": len(victims)}

    def save(self, body: dict) -> dict:
        voice = config.normalize_voice(body.get("voice"))
        language = config.normalize_language(body.get("language"))
        chunks = text.prepare(str(body.get("text", "")), language, clean=body.get("clean", True))
        path, fmt = audio.resolve_output_path(
            body.get("path"), body.get("format"), config.load_settings().output_dir,
            bool(body.get("overwrite", False)))
        with self._cond:
            self._saving += 1
            self._touch()
        try:
            pcm = [self._synth(c, voice, language) for c in chunks]
            duration = audio.write_audio(path, fmt, audio.join_pcm(pcm))
        finally:
            with self._cond:
                self._saving -= 1
                self._touch()
        return {"path": str(path), "duration": round(duration, 2), "format": fmt}

    def voices(self) -> dict:
        s = config.load_settings()
        return {"voices": list(config.VOICES), "languages": list(config.LANGUAGES),
                "default_voice": s.voice, "default_language": s.language}

    def snapshot(self) -> dict:
        with self._cond:
            p = self._playing
            return {
                "playing": p.id if p else None,
                "queued": [r.id for r in self._play_queue],
                "done": list(self._done),
                "progress": f"sentence {p.progress} of {len(p.chunks)}" if p else "",
                "errors": dict(self._errors),
            }

    def _record_error(self, req: Request, err: Exception) -> None:
        with self._cond:
            self._errors[req.id] = f"{type(err).__name__}: {err}" if not str(err) else str(err)
            while len(self._errors) > 50:
                self._errors.pop(next(iter(self._errors)))

    # -- threads -------------------------------------------------------------
    def _touch(self) -> None:
        self._last_activity = time.monotonic()

    def _synth(self, chunk: str, voice: str, language: str) -> bytes:
        with self._engine_lock:
            return self.engine.synthesize(chunk, voice, language)

    def _synth_loop(self) -> None:
        while True:
            with self._cond:
                while self._running and not self._synth_queue:
                    self._cond.wait()
                if not self._running:
                    return
                req = self._synth_queue[0]
            try:
                for chunk in req.chunks:
                    while req.audio.qsize() >= RUN_AHEAD and not req.cancelled and self._running:
                        time.sleep(0.05)
                    if req.cancelled or not self._running:
                        break
                    pcm = self._synth(chunk, req.voice, req.language)
                    if req.cancelled:
                        break
                    req.audio.put(pcm)
            except Exception as e:
                log.exception("synthesis failed for %s", req.id)
                self._record_error(req, e)
                req.cancelled = True
                req.audio.put(None)
            with self._cond:
                if self._synth_queue and self._synth_queue[0] is req:
                    self._synth_queue.popleft()

    def _play_loop(self) -> None:
        while True:
            with self._cond:
                while self._running and not self._play_queue:
                    self._cond.wait()
                if not self._running:
                    return
                req = self._play_queue.popleft()
                self._playing = req
            finished = False
            try:
                for i in range(len(req.chunks)):
                    pcm = req.audio.get()
                    if pcm is None or req.cancelled:
                        break
                    req.progress = i + 1
                    self.player.play(pcm, config.SAMPLE_RATE)
                    if req.cancelled:
                        break
                else:
                    finished = True
            except Exception as e:
                log.exception("playback failed for %s", req.id)
                self._record_error(req, e)
            finally:
                if not finished:
                    # Release the synth thread, which may be waiting on this request's run-ahead.
                    req.cancelled = True
                    req.audio.put(None)
            with self._cond:
                self._playing = None
                self._done.append(req.id)
                self._touch()

    def _idle_loop(self) -> None:
        while self._running:
            time.sleep(min(1.0, self.idle_timeout / 4))
            with self._cond:
                busy = self._playing or self._play_queue or self._synth_queue or self._saving
                idle_for = time.monotonic() - self._last_activity
            if not busy and idle_for >= self.idle_timeout:
                log.info("idle for %.0fs, shutting down", idle_for)
                self.shutdown()
                return

    def serve_forever(self) -> None:
        threading.Thread(target=self._warm_engine, daemon=True).start()
        for target in (self._synth_loop, self._play_loop, self._idle_loop):
            threading.Thread(target=target, daemon=True).start()
        log.info("daemon listening on 127.0.0.1:%s", self.port)
        try:
            self.httpd.serve_forever(poll_interval=0.2)
        finally:
            self.httpd.server_close()
            self.engine.stop()

    def _warm_engine(self) -> None:
        try:
            self.engine.start()
        except Exception:
            log.exception("engine failed to start")

    def shutdown(self) -> None:
        if not self._running:
            return
        self.stop()
        with self._cond:
            self._running = False
            self._cond.notify_all()
        threading.Thread(target=self.httpd.shutdown, daemon=True).start()

    # -- HTTP ----------------------------------------------------------------
    def _handler_class(self):
        daemon = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                log.debug(fmt, *args)

            def _send(self, code: int, payload: dict) -> None:
                data = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _route(self, routes: dict) -> None:
                fn = routes.get(self.path.split("?")[0])
                if fn is None:
                    return self._send(404, {"error": f"unknown route {self.path}"})
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    body = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
                    self._send(200, fn(body))
                except (ValueError, FileExistsError) as e:
                    self._send(400, {"error": str(e)})
                except Exception as e:
                    log.exception("request failed")
                    self._send(500, {"error": f"{type(e).__name__}: {e}"})

            def do_GET(self):
                self._route({"/status": lambda b: daemon.snapshot(),
                             "/voices": lambda b: daemon.voices()})

            def do_POST(self):
                self._route({"/speak": daemon.speak, "/stop": lambda b: daemon.stop(),
                             "/save": daemon.save})

        return Handler


def main(port: int = config.DAEMON_PORT) -> int:
    logging.basicConfig(
        filename=config.log_dir() / "daemon.log", level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    from .audio import Player
    from .engine import Engine

    try:
        dm = Daemon(Engine(), Player(), port=port)
    except OSError:
        log.info("port %s busy: another daemon is running", port)
        return 0
    dm.serve_forever()
    return 0
