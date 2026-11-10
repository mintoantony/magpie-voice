import pytest

from magpie_voice.text import clean_for_speech, prepare, split_chunks


def test_strips_markdown():
    assert clean_for_speech("## Title\n**bold** and *it* `x`") == "Title.\nbold and it x"


def test_link_keeps_text_drops_url():
    assert clean_for_speech("See [the docs](https://a.b/c) or https://x.y/z now") == "See the docs or now"


def test_code_block_replaced():
    assert "code block skipped" in clean_for_speech("Run:\n```py\nprint(1)\n```\nDone.").lower()


def test_bullets():
    assert clean_for_speech("- one\n- two") == "one.\ntwo."


def test_symbols_english():
    assert clean_for_speech("50% & $3.50", "en-US") == "50 percent and 3.50 dollars"


def test_symbols_untouched_non_english():
    assert "&" in clean_for_speech("A & B", "es-ES")


def test_split_on_sentences():
    assert split_chunks("One. Two? Three!") == ["One. Two? Three!"]


def test_split_respects_max():
    text = "This is a sentence of moderate length. " * 200
    chunks = split_chunks(text)
    assert all(len(c) <= 300 for c in chunks)
    assert "".join(chunks).replace(" ", "") == text.replace(" ", "")


def test_split_long_run_on():
    chunks = split_chunks("word " * 200)
    assert all(len(c) <= 300 for c in chunks) and len(chunks) >= 4


def test_split_hard_cut_without_spaces():
    chunks = split_chunks("x" * 700)
    assert all(len(c) <= 300 for c in chunks) and "".join(chunks) == "x" * 700


def test_prepare_nothing_left():
    for t in ["   ", "https://x.y/z", "```\nprint(1)\n```"]:
        with pytest.raises(ValueError, match="Nothing to speak"):
            prepare(t, "en-US")


def test_prepare_unicode():
    assert prepare("Ünïcødé café.", "fr-FR") == ["Ünïcødé café."]


def test_prepare_raw_keeps_symbols():
    assert prepare("A & B.", "en-US", clean=False) == ["A & B."]
