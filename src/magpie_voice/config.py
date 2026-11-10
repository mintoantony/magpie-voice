"""Paths, ports, voices, languages and user settings."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE_EXE = ROOT / "vendor" / "nemo-speech" / "nemo-speech-0.3.0-windows-x86_64-cpu" / "bin" / "nemo-speech.exe"
MODELS_DIR = ROOT / "models"
ENGINE_PORT = 47390
DAEMON_PORT = 47391
SAMPLE_RATE = 22050

VOICES: tuple[str, ...] = ("Aria", "Jason", "John", "Leo", "Sofia")
LANGUAGES: tuple[str, ...] = (
    "en-US", "es-ES", "de-DE", "fr-FR", "it-IT", "vi-VN",
    "hi-IN", "ar-AE", "ar-SA", "ar-MSA", "ko-KR", "pt-BR",
)
LANG_ALIASES: dict[str, str] = {
    "en": "en-US", "es": "es-ES", "de": "de-DE", "fr": "fr-FR", "it": "it-IT",
    "vi": "vi-VN", "hi": "hi-IN", "ko": "ko-KR", "pt": "pt-BR", "ar": "ar-MSA",
}

DEFAULT_VOICE = "Aria"
DEFAULT_LANGUAGE = "en-US"


def app_data_dir() -> Path:
    return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "MagpieVoice"


def log_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "MagpieVoice"
    base.mkdir(parents=True, exist_ok=True)
    return base


@dataclass
class Settings:
    voice: str = DEFAULT_VOICE
    language: str = DEFAULT_LANGUAGE
    output_dir: Path = Path.home() / "Documents" / "MagpieVoice"


def load_settings() -> Settings:
    s = Settings()
    path = app_data_dir() / "config.toml"
    if path.is_file():
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        if "voice" in data:
            s.voice = _match_voice(str(data["voice"]))
        if "language" in data:
            s.language = _match_language(str(data["language"]))
        if "output_dir" in data:
            s.output_dir = Path(os.path.expandvars(str(data["output_dir"]))).expanduser()
    return s


def _match_voice(name: str) -> str:
    for v in VOICES:
        if v.lower() == name.strip().lower():
            return v
    raise ValueError(f"Unknown voice '{name}'. Choose from: {', '.join(VOICES)}")


def _match_language(code: str) -> str:
    c = code.strip().lower()
    if c in LANG_ALIASES:
        return LANG_ALIASES[c]
    for lang in LANGUAGES:
        if lang.lower() == c:
            return lang
    raise ValueError(
        f"Unknown language '{code}'. Choose from: {', '.join(LANGUAGES)} "
        f"(or short codes {', '.join(LANG_ALIASES)})"
    )


def normalize_voice(name: str | None) -> str:
    return load_settings().voice if not name else _match_voice(name)


def normalize_language(code: str | None) -> str:
    return load_settings().language if not code else _match_language(code)
