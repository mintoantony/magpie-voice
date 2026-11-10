"""Audio files (WAV/MP3), output paths and playback."""

from __future__ import annotations

import threading
import time
import wave
from datetime import datetime
from pathlib import Path

from .config import SAMPLE_RATE

FORMATS = ("wav", "mp3")


def join_pcm(chunks: list[bytes], pause_ms: int = 250, sample_rate: int = SAMPLE_RATE) -> bytes:
    silence = b"\x00\x00" * int(sample_rate * pause_ms / 1000)
    return silence.join(chunks)


def _timestamped(folder: Path, ext: str) -> Path:
    stem = "magpie-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    path = folder / f"{stem}.{ext}"
    n = 2
    while path.exists():
        path = folder / f"{stem}-{n}.{ext}"
        n += 1
    return path


def resolve_output_path(path: str | None, fmt: str | None, output_dir: Path,
                        overwrite: bool) -> tuple[Path, str]:
    if fmt is not None:
        fmt = fmt.lower().lstrip(".")
        if fmt not in FORMATS:
            raise ValueError(f"Unsupported format '{fmt}'. Use wav or mp3.")
    if not path:
        target = _timestamped(Path(output_dir), fmt or "wav")
    else:
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = Path(output_dir) / p
        if p.is_dir():
            target = _timestamped(p, fmt or "wav")
        elif p.suffix:
            ext = p.suffix.lower().lstrip(".")
            if ext not in FORMATS:
                raise ValueError(f"Unsupported file type '.{ext}'. Use wav or mp3.")
            target = p
        else:
            target = p.with_name(p.name + "." + (fmt or "wav"))
    target = target.resolve()
    if target.exists() and not overwrite:
        raise FileExistsError(f"{target} already exists. Pass overwrite to replace it.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target, target.suffix.lower().lstrip(".")


def write_audio(path: Path, fmt: str, pcm: bytes, sample_rate: int = SAMPLE_RATE) -> float:
    path = Path(path)
    if fmt == "wav":
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(pcm)
    elif fmt == "mp3":
        import lameenc

        enc = lameenc.Encoder()
        enc.set_bit_rate(128)
        enc.set_in_sample_rate(sample_rate)
        enc.set_channels(1)
        enc.set_quality(2)
        path.write_bytes(enc.encode(pcm) + enc.flush())
    else:
        raise ValueError(f"Unsupported format '{fmt}'. Use wav or mp3.")
    return len(pcm) / 2 / sample_rate


class Player:
    """Plays PCM16 mono audio on the default output device; stop() works from any thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stopped = threading.Event()

    def play(self, pcm: bytes, sample_rate: int = SAMPLE_RATE) -> None:
        import numpy as np
        import sounddevice as sd

        if not pcm:
            return
        data = np.frombuffer(pcm, dtype="<i2")
        with self._lock:
            self._stopped.clear()
            sd.play(data, sample_rate)
        end = time.monotonic() + len(data) / sample_rate + 1.0
        # Poll instead of sd.wait() so stop() can interrupt promptly.
        while time.monotonic() < end and not self._stopped.is_set():
            stream = sd.get_stream()
            if not stream.active:
                break
            time.sleep(0.05)

    def stop(self) -> None:
        import sounddevice as sd

        with self._lock:
            self._stopped.set()
            sd.stop()
