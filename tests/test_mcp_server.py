import asyncio
import inspect

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from magpie_voice import mcp_server as m


class FakeClient:
    def speak(self, text, voice=None, language=None):
        return {"id": "r1", "position": 2, "chunks": 3}

    def stop(self):
        return {"stopped": 4}

    def save(self, text, path=None, voice=None, language=None, format=None, overwrite=False):
        return {"path": "C:\\out\\hello.mp3", "duration": 2.5, "format": "mp3"}

    def voices(self):
        return {"voices": ["Aria", "Sofia"], "languages": ["en-US", "es-ES"],
                "default_voice": "Aria", "default_language": "en-US"}


@pytest.fixture(autouse=True)
def fake(monkeypatch):
    monkeypatch.setattr(m, "client", FakeClient())


def test_speak_message():
    assert m.speak("Hello") == "Queued (position 2, 3 sentences)."


def test_stop_message():
    assert m.stop() == "Stopped. Dropped 4 request(s)."


def test_save_message_has_path():
    assert m.save_audio("Hello", "hello.mp3") == "Saved C:\\out\\hello.mp3 (2.5s, mp3)."


def test_list_voices_message():
    out = m.list_voices()
    assert "Sofia" in out and "es-ES" in out


def test_error_passthrough(monkeypatch):
    msg = "Unknown voice 'Bob'. Choose from: Aria, Jason, John, Leo, Sofia"

    def bad(*a, **k):
        raise ValueError(msg)
    monkeypatch.setattr(m.client, "speak", bad)
    with pytest.raises(ToolError, match="Choose from"):
        m.speak("hi", voice="Bob")


def test_daemon_failure_is_tool_error(monkeypatch):
    def bad(*a, **k):
        raise RuntimeError("Magpie Voice daemon did not start")
    monkeypatch.setattr(m.client, "save", bad)
    with pytest.raises(ToolError, match="did not start"):
        m.save_audio("hi")


def test_tools_registered():
    tools = m.server.list_tools()
    if inspect.isawaitable(tools):
        tools = asyncio.run(tools)
    assert {t.name for t in tools} == {"speak", "stop", "save_audio", "list_voices"}
