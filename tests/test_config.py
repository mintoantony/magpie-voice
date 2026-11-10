import pytest

from magpie_voice.config import load_settings, normalize_language, normalize_voice


def test_voice_case_insensitive():
    assert normalize_voice("sofia") == "Sofia"


def test_voice_unknown_lists_choices():
    with pytest.raises(ValueError, match="Aria.*Sofia"):
        normalize_voice("Bob")


def test_voice_none_uses_default(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert normalize_voice(None) == "Aria"


def test_language_alias_and_full():
    assert normalize_language("es") == "es-ES"
    assert normalize_language("PT-br") == "pt-BR"


def test_language_unknown():
    with pytest.raises(ValueError, match="en-US"):
        normalize_language("xx")


def test_defaults_without_config(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    s = load_settings()
    assert (s.voice, s.language) == ("Aria", "en-US")
    assert s.output_dir.name == "MagpieVoice"


def test_config_file_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    (tmp_path / "MagpieVoice").mkdir()
    (tmp_path / "MagpieVoice" / "config.toml").write_text('voice = "Leo"\n')
    assert load_settings().voice == "Leo"
