import wave

import pytest

from magpie_voice.audio import join_pcm, resolve_output_path, write_audio


def test_join_inserts_pause():
    a = b"\x01\x00" * 100
    out = join_pcm([a, a], pause_ms=250)
    assert len(out) == 400 + int(22050 * 0.25) * 2


def test_default_name(tmp_path):
    p, f = resolve_output_path(None, None, tmp_path, False)
    assert p.parent == tmp_path and p.suffix == ".wav" and f == "wav"


def test_folder_gets_timestamped_file(tmp_path):
    p, _ = resolve_output_path(str(tmp_path), None, tmp_path / "other", False)
    assert p.parent == tmp_path and p.name.startswith("magpie-")


def test_creates_missing_dir(tmp_path):
    p, f = resolve_output_path(str(tmp_path / "new" / "Ünï.mp3"), None, tmp_path, False)
    assert p.parent.is_dir() and p.suffix == ".mp3" and f == "mp3"


def test_no_extension_gets_wav(tmp_path):
    assert resolve_output_path(str(tmp_path / "x"), None, tmp_path, False)[0].suffix == ".wav"


def test_no_extension_uses_format(tmp_path):
    assert resolve_output_path(str(tmp_path / "x"), "mp3", tmp_path, False)[0].suffix == ".mp3"


def test_unsupported_extension(tmp_path):
    with pytest.raises(ValueError, match="wav or mp3"):
        resolve_output_path(str(tmp_path / "x.ogg"), None, tmp_path, False)


def test_refuses_overwrite(tmp_path):
    (tmp_path / "a.wav").write_bytes(b"x")
    with pytest.raises(FileExistsError):
        resolve_output_path(str(tmp_path / "a.wav"), None, tmp_path, False)


def test_allows_overwrite(tmp_path):
    (tmp_path / "a.wav").write_bytes(b"x")
    assert resolve_output_path(str(tmp_path / "a.wav"), None, tmp_path, True)[0].name == "a.wav"


def test_wav_roundtrip(tmp_path):
    d = write_audio(tmp_path / "a.wav", "wav", b"\x00\x00" * 22050)
    assert abs(d - 1.0) < 0.01
    with wave.open(str(tmp_path / "a.wav")) as w:
        assert w.getframerate() == 22050 and w.getnchannels() == 1


def test_mp3_written(tmp_path):
    write_audio(tmp_path / "a.mp3", "mp3", b"\x00\x00" * 22050)
    data = (tmp_path / "a.mp3").read_bytes()
    assert data[:3] == b"ID3" or (data[0] == 0xFF and data[1] & 0xE0 == 0xE0)
