"""magpie-voice command line."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import client


def _read_text(args) -> str:
    if getattr(args, "file", None):
        return Path(args.file).read_text(encoding="utf-8")
    if args.text == "-":
        return sys.stdin.read()
    if args.text:
        return args.text
    raise ValueError("No text given. Pass TEXT, '-' for stdin, or --file PATH.")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="magpie-voice",
                                description="Local text-to-speech with NVIDIA Magpie TTS.")
    sub = p.add_subparsers(dest="cmd", required=True)

    def text_args(sp):
        sp.add_argument("text", nargs="?", help="text to speak, or '-' to read stdin")
        sp.add_argument("--file", help="read text from a UTF-8 file")
        sp.add_argument("--voice", help="Aria, Jason, John, Leo or Sofia")
        sp.add_argument("--lang", help="language, e.g. en, es, de-DE")

    text_args(sub.add_parser("say", help="read text aloud"))
    sp = sub.add_parser("save", help="save speech to a WAV or MP3 file")
    text_args(sp)
    sp.add_argument("-o", "--output", help="output file or folder (default: Documents\\MagpieVoice)")
    sp.add_argument("--format", choices=["wav", "mp3"])
    sp.add_argument("--overwrite", action="store_true")
    sp.add_argument("--raw", action="store_true", help="do not strip Markdown/symbols")
    sub.add_parser("stop", help="stop speaking and clear the queue")
    sub.add_parser("voices", help="list voices and languages")
    sub.add_parser("gui", help="open the window")
    sub.add_parser("mcp", help="run the MCP server (used by Claude Code)")
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    args = _parser().parse_args(argv)
    try:
        if args.cmd == "say":
            r = client.speak(_read_text(args), args.voice, args.lang)
            try:
                client.wait_done(r["id"])
            except KeyboardInterrupt:
                client.stop()
                return 130
        elif args.cmd == "save":
            r = client.save(_read_text(args), args.output, args.voice, args.lang,
                            args.format, args.overwrite, not args.raw)
            print(r["path"])
        elif args.cmd == "stop":
            client.stop()
        elif args.cmd == "voices":
            v = client.voices()
            print("Voices:    " + ", ".join(v["voices"]) + f"  (default {v['default_voice']})")
            print("Languages: " + ", ".join(v["languages"]) + f"  (default {v['default_language']})")
        elif args.cmd == "gui":
            from .gui import run
            run()
        elif args.cmd == "mcp":
            from .mcp_server import run
            run()
    except (ValueError, RuntimeError, OSError, TimeoutError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0
