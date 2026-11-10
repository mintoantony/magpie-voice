import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from magpie_voice.client import Client
from magpie_voice.daemon import Daemon

CHUNK_SECONDS = 1.0


class FakeEngine:
    def __init__(self):
        self.calls = 0

    def start(self, timeout=0):
        pass

    def stop(self):
        pass

    def synthesize(self, text, voice, language):
        self.calls += 1
        time.sleep(0.05)
        return b"\x00\x00" * int(22050 * CHUNK_SECONDS)

    def voices(self):
        return {"voices": ["Aria"], "languages": ["en-US"]}


class FakePlayer:
    def __init__(self):
        self.played = []
        self.was_stopped = False
        self.daemon = None
        self._stop = threading.Event()

    def play(self, pcm, sample_rate):
        self.played.append((self.daemon.snapshot()["playing"], len(pcm)))
        self._stop.clear()
        self._stop.wait(len(pcm) / 2 / sample_rate)

    def stop(self):
        self.was_stopped = True
        self._stop.set()


def _start(port=0, idle_timeout=60, player=None):
    player = player or FakePlayer()
    dm = Daemon(FakeEngine(), player, port=port, idle_timeout=idle_timeout)
    player.daemon = dm
    th = threading.Thread(target=dm.serve_forever, daemon=True)
    th.start()
    return dm, th


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    state = {}
    dm, th = _start()
    state["dm"] = dm
    port = dm.port

    def spawn():
        state["dm"], _ = _start(port=port)

    client = Client(port=port, spawn=spawn)
    yield client, dm.player, state
    state["dm"].shutdown()


@pytest.fixture
def d(setup):
    return setup[0]


@pytest.fixture
def player(setup):
    return setup[1]


def test_speak_returns_immediately(d):
    t = time.monotonic()
    r = d.speak("One. Two. Three.")
    assert time.monotonic() - t < 0.5 and r["position"] == 0


def test_requests_play_whole_in_order(d, player):
    a = d.speak("A one. " * 60)["id"]
    b = d.speak("B one.")["id"]
    d.wait_done(b, timeout=30)
    owners = [rid for rid, _ in player.played]
    assert owners == sorted(owners, key=[a, b].index)
    assert owners.count(a) == 2 and owners.count(b) == 1


def test_stop_clears_everything(d, player):
    d.speak("x. " * 200)
    d.speak("y.")
    time.sleep(0.4)
    assert d.stop()["stopped"] == 2
    s = d.status()
    assert s["queued"] == [] and s["playing"] is None


def test_new_speak_does_not_interrupt(d, player):
    a = d.speak("first. " * 5)["id"]
    time.sleep(0.2)
    d.speak("second.")
    d.wait_done(a, timeout=30)
    assert not player.was_stopped


def test_save_bypasses_queue(d, tmp_path):
    d.speak("long. " * 100)
    t = time.monotonic()
    r = d.save("Saved text.", str(tmp_path / "s.wav"))
    assert time.monotonic() - t < 5 and Path(r["path"]).exists() and r["format"] == "wav"


def test_save_existing_file_errors(d, tmp_path):
    (tmp_path / "s.wav").write_bytes(b"x")
    with pytest.raises(ValueError, match="already exists"):
        d.save("Hi.", str(tmp_path / "s.wav"))


def test_bad_voice_400(d):
    with pytest.raises(ValueError, match="Sofia"):
        d.speak("hi", voice="Bob")


def test_nothing_to_speak(d):
    with pytest.raises(ValueError, match="Nothing to speak"):
        d.speak("   ")


def test_voices(d):
    v = d.voices()
    assert "Sofia" in v["voices"] and v["default_voice"] == "Aria"


def test_second_daemon_exits_when_port_taken(setup):
    port = setup[2]["dm"].port
    r = subprocess.run([sys.executable, "-m", "magpie_voice", "daemon", "--port", str(port)],
                       timeout=30, capture_output=True)
    assert r.returncode == 0
    with socket.create_connection(("127.0.0.1", port), timeout=2):
        pass  # original daemon still answering


def test_wait_done_survives_daemon_restart(setup):
    client, _, state = setup
    rid = client.speak("x. " * 50)["id"]
    state["dm"].shutdown()
    client.wait_done(rid, timeout=60)


def test_wait_done_times_out(d):
    rid = d.speak("x. " * 200)["id"]
    with pytest.raises(TimeoutError):
        d.wait_done(rid, timeout=0.5)


def test_idle_shutdown():
    dm, th = _start(idle_timeout=0.5)
    th.join(5)
    assert not th.is_alive()


class BrokenOncePlayer(FakePlayer):
    def __init__(self):
        super().__init__()
        self.fail_next = True

    def play(self, pcm, sample_rate):
        if self.fail_next:
            self.fail_next = False
            raise OSError("audio device disappeared")
        super().play(pcm, sample_rate)


def test_playback_error_does_not_wedge_queue(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    dm, _ = _start(player=BrokenOncePlayer())
    try:
        c = Client(port=dm.port, spawn=lambda: None)
        c.speak("x. " * 600)                       # many chunks; first play raises
        b = c.speak("after the error.")["id"]
        c.wait_done(b, timeout=20)                 # must not hang
    finally:
        dm.shutdown()


class FailingEngine(FakeEngine):
    def synthesize(self, text, voice, language):
        raise RuntimeError("engine exploded")


def test_synthesis_error_reported_to_waiter(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    player = FakePlayer()
    dm = Daemon(FailingEngine(), player, port=0)
    player.daemon = dm
    threading.Thread(target=dm.serve_forever, daemon=True).start()
    try:
        c = Client(port=dm.port, spawn=lambda: None)
        rid = c.speak("Hello.")["id"]
        with pytest.raises(RuntimeError, match="engine exploded"):
            c.wait_done(rid, timeout=10)
        assert "engine exploded" in c.status()["errors"][rid]
    finally:
        dm.shutdown()


class MissingEngine(FakeEngine):
    def available(self):
        return False


def test_speak_fails_fast_when_engine_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    player = FakePlayer()
    dm = Daemon(MissingEngine(), player, port=0)
    player.daemon = dm
    threading.Thread(target=dm.serve_forever, daemon=True).start()
    try:
        c = Client(port=dm.port, spawn=lambda: None)
        with pytest.raises(RuntimeError, match="setup.ps1"):
            c.speak("Hello.")
    finally:
        dm.shutdown()


def test_wait_done_gives_up_when_daemon_cannot_restart():
    c = Client(port=1, spawn=lambda: None, start_timeout=1)   # nothing listens on port 1
    t = time.monotonic()
    with pytest.raises(RuntimeError, match="did not start"):
        c.wait_done("abc", timeout=None)
    assert time.monotonic() - t < 10


def test_spawn_breaks_away_from_job_with_fallback(monkeypatch):
    import subprocess as sp
    from magpie_voice import client as client_mod
    calls = []

    def fake_popen(args, **kw):
        calls.append(kw["creationflags"])
        if len(calls) == 1:
            raise OSError("access denied: job forbids breakaway")
        return object()
    monkeypatch.setattr(client_mod.subprocess, "Popen", fake_popen)
    client_mod._spawn_daemon(47391)
    assert calls[0] & sp.CREATE_BREAKAWAY_FROM_JOB
    assert not calls[1] & sp.CREATE_BREAKAWAY_FROM_JOB
