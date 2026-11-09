import pytest

from magpie_voice import config

pytestmark = [
    pytest.mark.engine,
    pytest.mark.skipif(
        not config.ENGINE_EXE.exists() or not (config.MODELS_DIR / "nvidia").exists(),
        reason="engine or models not installed",
    ),
]


@pytest.fixture(scope="module")
def engine():
    from magpie_voice.engine import Engine

    e = Engine(port=47399)  # separate port so a running daemon is not disturbed
    e.start()
    yield e
    e.stop()


def test_synthesize_english(engine):
    pcm = engine.synthesize("Hello there.", "Aria", "en-US")
    assert 0.5 < len(pcm) / 2 / 22050 < 5


@pytest.mark.parametrize("v", ["Aria", "Jason", "John", "Leo", "Sofia"])
def test_each_voice(engine, v):
    assert len(engine.synthesize("Test.", v, "en-US")) > 2000


def test_unicode_spanish(engine):
    assert len(engine.synthesize("¿Qué tal? Añadir café.", "Sofia", "es-ES")) > 2000


def test_voices_listing(engine):
    assert set(engine.voices()["voices"]) == {"Aria", "Jason", "John", "Leo", "Sofia"}


def test_unknown_voice_is_value_error(engine):
    with pytest.raises(ValueError):
        engine.synthesize("Hi.", "Bob", "en-US")


def test_restarts_after_engine_dies(engine):
    engine._proc.kill()
    engine._proc.wait()
    assert len(engine.synthesize("Back again.", "Aria", "en-US")) > 2000
