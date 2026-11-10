import io
from pathlib import Path

import pytest

from magpie_voice import cli


class FakeClient:
    def __init__(self):
        self.calls = []

    def speak(self, text, voice=None, language=None):
        self.calls.append(("speak", text, voice, language))
        return {"id": "r1", "position": 0, "chunks": 1}

    def wait_done(self, rid, timeout=None):
        self.calls.append(("wait_done", rid))

    def stop(self):
        self.calls.append(("stop",))
        return {"stopped": 1}

    def save(self, text, path=None, voice=None, language=None, format=None, overwrite=False, clean=True):
        self.calls.append(("save", text, path, voice, language, format, overwrite, clean))
        return {"path": "C:\\out\\a.wav", "duration": 1.0, "format": "wav"}

    def voices(self):
        return {"voices": ["Aria", "Sofia"], "languages": ["en-US"],
                "default_voice": "Aria", "default_language": "en-US"}


@pytest.fixture
def fc(monkeypatch):
    f = FakeClient()
    monkeypatch.setattr(cli, "client", f)
    return f


def test_say_waits_for_done(fc):
    assert cli.main(["say", "Hello", "--voice", "Sofia", "--lang", "es"]) == 0
    assert fc.calls == [("speak", "Hello", "Sofia", "es"), ("wait_done", "r1")]


def test_say_reads_stdin_dash(fc, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("From stdin"))
    cli.main(["say", "-"])
    assert fc.calls[0][1] == "From stdin"


def test_say_ctrl_c_stops(fc, monkeypatch):
    def boom(rid, timeout=None):
        raise KeyboardInterrupt
    monkeypatch.setattr(fc, "wait_done", boom)
    assert cli.main(["say", "Hi"]) == 130
    assert ("stop",) in fc.calls


def test_save_prints_path(fc, capsys):
    assert cli.main(["save", "Hello", "-o", "a.wav", "--format", "wav", "--overwrite", "--raw"]) == 0
    assert "C:\\out\\a.wav" in capsys.readouterr().out
    assert fc.calls[0] == ("save", "Hello", str(Path("a.wav").absolute()), None, None, "wav", True, False)


def test_save_file_option_utf8(fc, tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("Ünïcødé.", encoding="utf-8")
    cli.main(["save", "--file", str(f), "-o", "x.mp3"])
    assert fc.calls[0][1] == "Ünïcødé."


def test_error_returns_2_with_message(fc, monkeypatch, capsys):
    def bad(*a, **k):
        raise ValueError("Unknown voice")
    monkeypatch.setattr(fc, "speak", bad)
    assert cli.main(["say", "Hi"]) == 2
    assert "error: Unknown voice" in capsys.readouterr().err


def test_no_text_given_errors(fc, capsys):
    assert cli.main(["say"]) == 2
    assert "error:" in capsys.readouterr().err


def test_voices_lists(fc, capsys):
    assert cli.main(["voices"]) == 0
    out = capsys.readouterr().out
    assert "Sofia" in out and "en-US" in out


def test_save_relative_output_is_from_current_dir(fc, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli.main(["save", "Hi", "-o", "hello.wav"])
    assert fc.calls[0][2] == str(tmp_path / "hello.wav")
