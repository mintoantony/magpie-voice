"""MCP server (stdio) exposing Magpie Voice to Claude."""

from __future__ import annotations

import functools

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import client


def _friendly(fn):
    """Turn expected failures into ToolError so Claude sees the real message."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (ValueError, RuntimeError, OSError, TimeoutError, httpx.HTTPError) as e:
            raise ToolError(str(e)) from e
    return wrapper

server = MCPServer(
    name="magpie-voice",
    instructions=(
        "Local text-to-speech (NVIDIA Magpie TTS, offline). Use speak to read text aloud on the "
        "user's speakers and save_audio to write a WAV/MP3 file. Pass plain spoken text: no "
        "Markdown tables or code. Voices: Aria, Jason, John, Leo, Sofia."
    ),
)


@server.tool()
@_friendly
def speak(text: str, voice: str | None = None, language: str | None = None) -> str:
    """Read text aloud on the user's speakers. Returns immediately; audio plays in the
    background, queued behind other requests from any app or Claude session.
    voice: Aria, Jason, John, Leo or Sofia. language: e.g. en, es, de, fr, it, pt, hi, ko, vi, ar."""
    r = client.speak(text, voice, language)
    return f"Queued (position {r['position']}, {r['chunks']} sentences)."


@server.tool()
@_friendly
def stop() -> str:
    """Stop speaking now and clear every waiting read-aloud request on this PC."""
    r = client.stop()
    return f"Stopped. Dropped {r['stopped']} request(s)."


@server.tool()
@_friendly
def save_audio(text: str, path: str | None = None, voice: str | None = None,
               language: str | None = None, format: str | None = None,
               overwrite: bool = False) -> str:
    """Synthesize text to an audio file and wait until it is written. path: file or folder
    (relative paths go under Documents\\MagpieVoice; default is a timestamped .wav there).
    format: wav or mp3 (taken from the extension when omitted). Returns the absolute path."""
    r = client.save(text, path, voice, language, format, overwrite)
    return f"Saved {r['path']} ({r['duration']}s, {r['format']})."


@server.tool()
@_friendly
def list_voices() -> str:
    """List the available voices and languages and the current defaults."""
    v = client.voices()
    return (f"Voices: {', '.join(v['voices'])} (default {v['default_voice']}). "
            f"Languages: {', '.join(v['languages'])} (default {v['default_language']}).")


def run() -> None:
    server.run("stdio")
