import tkinter as tk

import pytest

from magpie_voice import gui


class FakeClient:
    def __init__(self):
        self.calls = []

    def voices(self):
        return {"voices": ["Aria", "Sofia"], "languages": ["en-US", "es-ES"],
                "default_voice": "Aria", "default_language": "en-US"}

    def speak(self, text, voice=None, language=None):
        self.calls.append(("speak", text, voice, language))
        return {"id": "r1", "position": 0, "chunks": 2}

    def stop(self):
        self.calls.append(("stop",))
        return {"stopped": 1}

    def save(self, text, path=None, voice=None, language=None, format=None, overwrite=False):
        self.calls.append(("save", text, path, voice, language, overwrite))
        return {"path": path, "duration": 1.2, "format": "wav"}

    def status(self):
        return {"playing": None, "queued": [], "done": ["r1"], "progress": ""}


@pytest.fixture(scope="module")
def tk_root():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def app(tk_root):
    win = tk.Toplevel(tk_root)
    win.withdraw()
    a = gui.App(win, client=FakeClient(), background=False)
    yield a
    win.destroy()


def test_speak_sends_text_voice_language(app):
    app.text.insert("1.0", "Hello there")
    app.voice.set("Sofia")
    app.language.set("es-ES")
    app.on_speak()
    assert app.client.calls[0] == ("speak", "Hello there", "Sofia", "es-ES")


def test_empty_text_shows_error_without_calling_client(app):
    app.on_speak()
    assert app.client.calls == []
    assert "Type or paste" in app.status_var.get()


def test_save_reports_path_in_status(app, tmp_path):
    app.text.insert("1.0", "Save me")
    p = str(tmp_path / "out.wav")
    app.on_save(p)
    assert app.client.calls[0][:3] == ("save", "Save me", p)
    assert app.client.calls[0][5] is True  # dialog already confirmed any overwrite
    assert p in app.status_var.get()


def test_stop_calls_client(app):
    app.on_stop()
    assert ("stop",) in app.client.calls


def test_client_error_shown_in_status(app):
    def bad(*a, **k):
        raise ValueError("Unknown voice")
    app.client.speak = bad
    app.text.insert("1.0", "Hi")
    app.on_speak()
    assert "Unknown voice" in app.status_var.get()
