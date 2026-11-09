"""Turn chat-style text (Markdown, code, links) into speakable chunks."""

from __future__ import annotations

import re

CODE_NOTE = "Code block skipped."

_FENCE = re.compile(r"```.*?(?:```|\Z)", re.S)
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_URL = re.compile(r"\b(?:https?://|www\.)\S+", re.I)
_INLINE_CODE = re.compile(r"`([^`]*)`")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*(.*)$")
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")
_EMPHASIS = re.compile(r"(\*\*|__|\*)(.+?)\1")
_SENTENCE_END = re.compile(r"[.!?…:;]$")


def _english_symbols(line: str) -> str:
    line = re.sub(r"\$\s?(\d[\d,]*(?:\.\d+)?)", r"\1 dollars", line)
    line = re.sub(r"(\d)\s?%", r"\1 percent", line)
    line = line.replace("%", " percent")
    line = re.sub(r"\s*&\s*", " and ", line)
    line = re.sub(r"(\d)\s?°\s?C\b", r"\1 degrees Celsius", line)
    line = re.sub(r"(\d)\s?°\s?F\b", r"\1 degrees Fahrenheit", line)
    line = line.replace("°", " degrees")
    return line


def clean_for_speech(text: str, language: str = "en-US") -> str:
    has_code = bool(_FENCE.search(text))
    text = _FENCE.sub(f"\n{CODE_NOTE}\n", text)
    text = _LINK.sub(r"\1", text)
    text = _URL.sub("", text)
    text = _INLINE_CODE.sub(r"\1", text)

    lines: list[str] = []
    for raw in text.splitlines():
        line = raw
        m = _HEADING.match(line) or _BULLET.match(line)
        structural = bool(m)
        if m:
            line = m.group(1)
        line = _EMPHASIS.sub(r"\2", line)
        line = re.sub(r"^\s*>\s?", "", line)  # block quotes
        line = line.replace("|", " ")          # table pipes
        if language.lower().startswith("en"):
            line = _english_symbols(line)
        line = re.sub(r"\s+", " ", line).strip()
        if not line or re.fullmatch(r"[-=_*\s]+", line):
            continue
        if structural and not _SENTENCE_END.search(line):
            line += "."
        lines.append(line)

    if has_code and all(line == CODE_NOTE for line in lines):
        lines = []
    return "\n".join(lines)


def _pack(pieces: list[str], max_chars: int) -> list[str]:
    chunks: list[str] = []
    cur = ""
    for p in pieces:
        if not cur:
            cur = p
        elif len(cur) + 1 + len(p) <= max_chars:
            cur = f"{cur} {p}"
        else:
            chunks.append(cur)
            cur = p
    if cur:
        chunks.append(cur)
    return chunks


def _split_long(sentence: str, max_chars: int) -> list[str]:
    if len(sentence) <= max_chars:
        return [sentence]
    for pattern in (r"(?<=[,;:])\s+", r"\s+"):
        parts = [p for p in re.split(pattern, sentence) if p]
        if len(parts) > 1:
            out: list[str] = []
            for chunk in _pack(parts, max_chars):
                out.extend(_split_long(chunk, max_chars))
            return out
    return [sentence[i:i + max_chars] for i in range(0, len(sentence), max_chars)]


def split_chunks(text: str, max_chars: int = 300) -> list[str]:
    sentences = [s for s in re.split(r"(?<=[.!?…])\s+|\n+", text.strip()) if s.strip()]
    pieces: list[str] = []
    for s in sentences:
        pieces.extend(_split_long(s.strip(), max_chars))
    return _pack(pieces, max_chars)


def prepare(text: str, language: str, clean: bool = True) -> list[str]:
    if clean:
        text = clean_for_speech(text, language)
    chunks = split_chunks(text)
    if not chunks:
        raise ValueError("Nothing to speak after clean-up")
    return chunks
