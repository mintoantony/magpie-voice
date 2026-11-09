# Magpie Voice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a local Windows text-to-speech app using NVIDIA Magpie TTS (through NeMo-Speech.cpp, GGUF, CPU). It reads text aloud and saves WAV/MP3 files, and you can drive it from Claude (MCP server + skill), a CLI or a small Tkinter window.

**Architecture:**
- One Python **speaker daemon** per PC (`127.0.0.1:47391`) owns everything shared:
  - a warm `nemo-speech serve` child process (`127.0.0.1:47390`),
  - the single PC-wide read-aloud queue, and the audio player.
- The MCP server, CLI and window are thin clients. They start the daemon if it isn't running (binding the port acts as the lock) and talk to it over local HTTP/JSON.
- The daemon shuts itself and the engine down after 30 minutes idle.

**Tech Stack:**
- Python 3.12 (uv project), `mcp` (FastMCP), `numpy`, `sounddevice`, `lameenc`, `httpx`, Tkinter, and the standard-library `http.server`/`argparse`.
- NeMo-Speech.cpp 0.3.0 `windows-x86_64-cpu`, run as a child process.
- Tests: pytest.

**Spec:** `docs/superpowers/specs/2026-11-06-magpie-voice-design.md`. Engine facts: `docs/engine-spike.md`.

## Global Constraints

- Windows 11, CPU only. Never import or install NeMo, PyTorch or CUDA.
- Everything lives under `D:\VanguardProjects\Agents\Text2Voice`. The engine is at `vendor/nemo-speech/nemo-speech-0.3.0-windows-x86_64-cpu/bin/nemo-speech.exe` and models are in `models/` (always set `NEMO_SPEECH_MODEL_DIR` to it). Never change the global PATH.
- Engine HTTP: `nemo-speech serve --host 127.0.0.1 --port 47390 --no-ui --tts-model magpie`, then `POST /v1/audio/speech {"input","voice","language","response_format":"pcm"}`. The reply is mono PCM16 at 22050 Hz.
- Voices: `Aria, Jason, John, Leo, Sofia` (case-insensitive). The default voice is `Aria`.
- Languages, as accepted by the engine: `en-US es-ES de-DE fr-FR it-IT vi-VN hi-IN ar-AE ar-SA ar-MSA ko-KR pt-BR`.
  - Short aliases: `en→en-US es→es-ES de→de-DE fr→fr-FR it→it-IT vi→vi-VN hi→hi-IN ko→ko-KR pt→pt-BR ar→ar-MSA`.
  - The default language is `en-US`.
- Daemon port: `47391`. Engine port: `47390`. Both bind to `127.0.0.1` only.
- Default output folder: `%USERPROFILE%\Documents\MagpieVoice\`. Config file: `%APPDATA%\MagpieVoice\config.toml`, with optional keys `voice`, `language` and `output_dir`.
- Pause between sentences in saved files: 250 ms. Maximum characters per engine call: 300.
- `speak` never blocks the caller until playback. A new `speak` never interrupts audio that's playing. Stop clears the PC-wide queue.
- Saved files are never silently overwritten unless `overwrite=True`.

## Review Focus

1. **Text with nothing speakable** (empty, only whitespace, only a code block or a URL) gives a clear error such as "Nothing to speak after clean-up". It must not produce silence or crash the engine. → Task 2 and Task 5 tests.
2. **Unknown voice or language** (`"sofia"` lower-case is valid; `"Bob"` and `"xx"` are not) gives an error that lists the valid choices, raised *before* anything is queued. → Task 1 test.
3. **Very long text** (5,000+ characters, or one sentence longer than 300 characters with no full stops) is split so that no engine call gets more than 300 characters. → Task 2 test.
4. **The daemon isn't running, or died while a client waits** (for example the CLI's `say`). The client starts it again or reports a clear error within 60 s. It never hangs forever. → Task 5 test.
5. **Save paths:** a folder that doesn't exist yet (create it), an existing file without `overwrite` (error), no extension (add `.wav`), `.mp3` (MP3 output), and non-ASCII characters in the path or text (`Ünïcødé`). → Task 3 and Task 4 tests.

---

### Task 1: Project scaffold, config and voices

**Files:**
- Create: `pyproject.toml`, `.python-version` (`3.12`), `.gitignore` (`vendor/`, `models/`, `spike/`, `.superpowers/`, `.venv/`, `__pycache__/`), `src/magpie_voice/__init__.py`, `src/magpie_voice/__main__.py`, `src/magpie_voice/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  - `config.ROOT: Path`, `config.ENGINE_EXE: Path`, `config.MODELS_DIR: Path`, `config.ENGINE_PORT = 47390`, `config.DAEMON_PORT = 47391`, `config.SAMPLE_RATE = 22050`
  - `config.VOICES: tuple[str, ...]`, `config.LANGUAGES: tuple[str, ...]`, `config.LANG_ALIASES: dict[str, str]`
  - `config.normalize_voice(name: str | None) -> str` (canonical capitalisation; `None` → the configured default; raises `ValueError` listing the voices)
  - `config.normalize_language(code: str | None) -> str` (alias or full code, case-insensitive; `None` → the default; raises `ValueError` listing the languages)
  - `config.Settings` (a dataclass with `voice`, `language`, `output_dir: Path`) and `config.load_settings() -> Settings`, which reads `%APPDATA%\MagpieVoice\config.toml` with `tomllib` (a missing file gives the defaults)
- The `pyproject` console script is `magpie-voice = "magpie_voice.cli:main"`.

- [ ] **Step 1:** Run `git init`, then `uv init --package --name magpie-voice --python 3.12`, keeping the `src/` layout. Run `uv add mcp numpy sounddevice lameenc httpx` and `uv add --dev pytest`. Expected: `uv sync` succeeds. If `lameenc` has no wheel, note it in the commit and leave MP3 to Task 3's fallback.
- [ ] **Step 2: Write the failing tests**

```python
def test_voice_case_insensitive():
    assert normalize_voice("sofia") == "Sofia"
def test_voice_unknown_lists_choices():
    with pytest.raises(ValueError, match="Aria.*Sofia"): normalize_voice("Bob")
def test_language_alias_and_full():
    assert normalize_language("es") == "es-ES"
    assert normalize_language("PT-br") == "pt-BR"
def test_language_unknown():
    with pytest.raises(ValueError, match="en-US"): normalize_language("xx")
def test_defaults_without_config(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    s = load_settings()
    assert (s.voice, s.language) == ("Aria", "en-US")
    assert s.output_dir.name == "MagpieVoice"
def test_config_file_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    (tmp_path/"MagpieVoice").mkdir(); (tmp_path/"MagpieVoice"/"config.toml").write_text('voice = "Leo"\n')
    assert load_settings().voice == "Leo"
```

- [ ] **Step 3:** Run `uv run pytest tests/test_config.py -v`. Expected: FAIL (import error).
- [ ] **Step 4:** Implement `config.py` as specified in Interfaces. `ROOT` is three levels up from `config.py`.
- [ ] **Step 5:** Run `uv run pytest tests/test_config.py -v`. Expected: PASS.
- [ ] **Step 6:** Commit the spec, the spike doc, this plan and the scaffold: `git commit -m "feat: project scaffold and voice/language config"`

### Task 2: Text clean-up and chunking

**Files:**
- Create: `src/magpie_voice/text.py`
- Test: `tests/test_text.py`

**Interfaces:**
- Produces:
  - `clean_for_speech(text: str, language: str = "en-US") -> str`
  - `split_chunks(text: str, max_chars: int = 300) -> list[str]`
  - `prepare(text: str, language: str, clean: bool = True) -> list[str]`, which cleans (if asked), splits, and raises `ValueError("Nothing to speak after clean-up")` when no chunk is left

- [ ] **Step 1: Write the failing tests**

```python
def test_strips_markdown():
    assert clean_for_speech("## Title\n**bold** and *it* `x`") == "Title.\nbold and it x"
def test_link_keeps_text_drops_url():
    assert clean_for_speech("See [the docs](https://a.b/c) or https://x.y/z now") == "See the docs or now"
def test_code_block_replaced():
    assert "code block skipped" in clean_for_speech("Run:\n```py\nprint(1)\n```\nDone.")
def test_bullets():
    assert clean_for_speech("- one\n- two") == "one.\ntwo."
def test_symbols_english():
    assert clean_for_speech("50% & $3.50", "en-US") == "50 percent and 3.50 dollars"
def test_symbols_untouched_non_english():
    assert "&" in clean_for_speech("A & B", "es-ES")
def test_split_on_sentences():
    assert split_chunks("One. Two? Three!") == ["One. Two? Three!"]   # merged: short
def test_split_respects_max():
    text = ("This is a sentence of moderate length. " * 200)
    chunks = split_chunks(text)
    assert all(len(c) <= 300 for c in chunks) and "".join(chunks).replace(" ", "") == text.replace(" ", "")
def test_split_long_run_on():
    chunks = split_chunks("word " * 200)   # no full stops, 1000 chars
    assert all(len(c) <= 300 for c in chunks) and len(chunks) >= 4
def test_prepare_nothing_left():
    for t in ["   ", "https://x.y/z", "```\nprint(1)\n```"]:
        with pytest.raises(ValueError, match="Nothing to speak"): prepare(t, "en-US")
def test_prepare_unicode():
    assert prepare("Ünïcødé café.", "fr-FR") == ["Ünïcødé café."]
```

- [ ] **Step 2:** Run `uv run pytest tests/test_text.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement with `re`.
  - Headings and list items each become a sentence ending in ".".
  - When the input contains only a code block, the "code block skipped" note is dropped.
  - Chunking is greedy: pack whole sentences up to `max_chars`. Split an oversized sentence at `, ; :`, then at spaces, then hard-cut.
- [ ] **Step 4:** Run `uv run pytest tests/test_text.py -v`. Expected: PASS.
- [ ] **Step 5:** `git commit -m "feat: speech text clean-up and chunking"`

### Task 3: Audio output (files and playback)

**Files:**
- Create: `src/magpie_voice/audio.py`
- Test: `tests/test_audio.py`

**Interfaces:**
- Consumes: `config.SAMPLE_RATE`.
- Produces:
  - `join_pcm(chunks: list[bytes], pause_ms: int = 250, sample_rate: int = 22050) -> bytes`
  - `resolve_output_path(path: str | None, fmt: str | None, output_dir: Path, overwrite: bool) -> tuple[Path, str]`, which returns the absolute path and `"wav"|"mp3"`:
    - `None` → `output_dir/magpie-YYYYmmdd-HHMMSS.wav`
    - a folder → a timestamped file inside it
    - no extension → `fmt` or `.wav`
    - creates parent folders
    - raises `FileExistsError` if the file exists and `overwrite` is False
  - `write_audio(path: Path, fmt: str, pcm: bytes, sample_rate: int = 22050) -> float` (returns the duration in seconds; WAV through the `wave` module, MP3 through `lameenc` at 128 kbps mono)
  - `class Player` with `play(pcm: bytes, sample_rate: int) -> None` (blocks until finished or stopped; `sounddevice.play` + `wait`) and `stop() -> None` (thread-safe; makes `play` return early)

- [ ] **Step 1: Write the failing tests**

```python
def test_join_inserts_pause():
    a = b"\x01\x00" * 100; out = join_pcm([a, a], pause_ms=250)
    assert len(out) == 400 + int(22050 * 0.25) * 2
def test_default_name(tmp_path):
    p, f = resolve_output_path(None, None, tmp_path, False)
    assert p.parent == tmp_path and p.suffix == ".wav" and f == "wav"
def test_creates_missing_dir(tmp_path):
    p, _ = resolve_output_path(str(tmp_path/"new"/"Ünï.mp3"), None, tmp_path, False)
    assert p.parent.is_dir() and p.suffix == ".mp3"
def test_no_extension_gets_wav(tmp_path):
    assert resolve_output_path(str(tmp_path/"x"), None, tmp_path, False)[0].suffix == ".wav"
def test_refuses_overwrite(tmp_path):
    (tmp_path/"a.wav").write_bytes(b"x")
    with pytest.raises(FileExistsError): resolve_output_path(str(tmp_path/"a.wav"), None, tmp_path, False)
def test_wav_roundtrip(tmp_path):
    d = write_audio(tmp_path/"a.wav", "wav", b"\x00\x00" * 22050)
    assert abs(d - 1.0) < 0.01 and wave.open(str(tmp_path/"a.wav")).getframerate() == 22050
def test_mp3_written(tmp_path):
    write_audio(tmp_path/"a.mp3", "mp3", b"\x00\x00" * 22050)
    data = (tmp_path/"a.mp3").read_bytes()
    assert data[:3] == b"ID3" or (data[0] == 0xFF and data[1] & 0xE0 == 0xE0)   # MP3 frame sync
```

- [ ] **Step 2:** Run `uv run pytest tests/test_audio.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement as in Interfaces. `Player.stop` calls `sounddevice.stop()` under a lock.
- [ ] **Step 4:** Run `uv run pytest tests/test_audio.py -v`. Expected: PASS. Then run a manual check: `uv run python -c "from magpie_voice.audio import Player; import numpy as n; Player().play((n.sin(n.arange(22050)*0.06)*8000).astype('<i2').tobytes(), 22050)"`, which should play a 1 s tone.
- [ ] **Step 5:** `git commit -m "feat: wav/mp3 writing, output paths, playback"`

### Task 4: Engine adapter

**Files:**
- Create: `src/magpie_voice/engine.py`
- Test: `tests/test_engine.py` (the tests are marked `@pytest.mark.engine` and skipped when `config.ENGINE_EXE` or `config.MODELS_DIR/nvidia` is missing; register the marker in `pyproject.toml`)

**Interfaces:**
- Consumes: `config.*`.
- Produces: `class Engine` with:
  - `start(timeout: float = 120) -> None`
    - Starts the serve command from Global Constraints, with `NEMO_SPEECH_MODEL_DIR`, `CREATE_NO_WINDOW`, and stderr sent to `%LOCALAPPDATA%\MagpieVoice\engine.log`.
    - Polls `GET /health`.
    - If the port already answers `/health`, it reuses that server.
  - `synthesize(text: str, voice: str, language: str) -> bytes` (PCM16 at 22050 Hz)
    - Uses `httpx`, timeout 120 s.
    - A 400 becomes `ValueError(body)`.
    - If the connection fails, it calls `start()` once and retries.
  - `voices() -> dict` (`{"voices": [...], "languages": [...]}` from `GET /v1/models`)
  - `stop() -> None` (terminates the child it started)

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.engine
def test_synthesize_english(engine):         # module fixture: Engine(); start(); yield; stop()
    pcm = engine.synthesize("Hello there.", "Aria", "en-US")
    assert 0.5 < len(pcm) / 2 / 22050 < 5
@pytest.mark.engine
@pytest.mark.parametrize("v", ["Aria", "Jason", "John", "Leo", "Sofia"])
def test_each_voice(engine, v):
    assert len(engine.synthesize("Test.", v, "en-US")) > 2000
@pytest.mark.engine
def test_unicode_spanish(engine):
    assert len(engine.synthesize("¿Qué tal? Añadir café.", "Sofia", "es-ES")) > 2000
@pytest.mark.engine
def test_voices_listing(engine):
    assert set(engine.voices()["voices"]) == {"Aria", "Jason", "John", "Leo", "Sofia"}
```

- [ ] **Step 2:** Run `uv run pytest tests/test_engine.py -v`. Expected: FAIL (import error).
- [ ] **Step 3:** Implement `Engine` as in Interfaces.
- [ ] **Step 4:** Run `uv run pytest tests/test_engine.py -v`. Expected: 8 PASS, taking up to about 60 s. Confirm `Get-Process nemo-speech` is gone afterwards.
- [ ] **Step 5:** `git commit -m "feat: NeMo-Speech engine adapter over local HTTP"`

### Task 5: Speaker daemon and client (the PC-wide queue)

**Files:**
- Create: `src/magpie_voice/daemon.py`, `src/magpie_voice/client.py`
- Test: `tests/test_daemon.py` (it uses a `FakeEngine` that returns 0.3 s of silence per chunk, plus a `FakePlayer` that records what it plays and sleeps for the clip's duration; the daemon is built in-process on an ephemeral port)

**Interfaces:**
- Consumes: `Engine`, `Player`, `text.prepare`, `audio.join_pcm/resolve_output_path/write_audio`, `config.normalize_*`, `config.load_settings`.
- Produces:
  - `daemon.Daemon(engine, player, port: int = 47391, idle_timeout: float = 1800)` with `.serve_forever()` and `.shutdown()`
  - The HTTP JSON routes, all on 127.0.0.1:

| Route | Body | Response |
|---|---|---|
| `POST /speak` | `{text, voice?, language?}` | `{"id": str, "position": int, "chunks": int}` — returns at once, after validation and `prepare` |
| `POST /stop` | — | `{"stopped": int}` (number of requests dropped, including the one playing) |
| `POST /save` | `{text, path?, voice?, language?, format?, overwrite?: bool, clean?: bool}` | `{"path", "duration", "format"}` — blocks until written; doesn't use the play queue |
| `GET /voices` | — | `{"voices", "languages", "default_voice", "default_language"}` |
| `GET /status` | — | `{"playing": id\|null, "queued": [id...], "done": [last 50 ids], "progress": "sentence i of n"}` |

  - Errors return HTTP 400 `{"error": "<plain message>"}`.
- **Pipeline:**
  - One playback thread takes requests in first-in, first-out order and plays each request's chunks in order. It never mixes in chunks from another request.
  - One synthesis thread produces chunks in queue order and can run ahead of playback, up to 3 chunks.
  - Stop sets a cancel generation: it drops queued requests, calls `player.stop()`, and the synthesis thread throws away anything already in flight.
  - Saves synthesize on the caller's handler thread. `ThreadingHTTPServer` is fine, and `Engine` calls are serialized with a lock.
- **Idle:** when nothing is queued, playing or saving for `idle_timeout`, the daemon stops the engine and exits.
- `client.py`:
  - `ensure_daemon(timeout: float = 60) -> None`: if `GET /status` fails, it spawns `pythonw.exe -m magpie_voice daemon` (the venv's pythonw, `DETACHED_PROCESS | CREATE_NO_WINDOW`) and polls until it's up. Otherwise it raises `RuntimeError("Magpie Voice daemon did not start; see %LOCALAPPDATA%\\MagpieVoice\\daemon.log")`.
  - `speak(text, voice=None, language=None) -> dict`, `stop() -> dict`, `save(text, path=None, voice=None, language=None, format=None, overwrite=False) -> dict`, `voices() -> dict`, `status() -> dict`, and `wait_done(request_id, timeout=None) -> None`, which polls `/status` every 0.3 s and calls `ensure_daemon` again if the connection drops. If the daemon restarted and the id is unknown, it returns.
  - Each call runs `ensure_daemon` first. 400 responses become `ValueError(error)`.
- `__main__.py` sends `daemon` to `Daemon(Engine(), Player()).serve_forever()`. Binding a busy port means another daemon is running, so it exits 0.

- [ ] **Step 1: Write the failing tests**

```python
def test_speak_returns_immediately(d):                   # d: client bound to in-process daemon
    t = time.monotonic(); r = d.speak("One. Two. Three."); assert time.monotonic() - t < 0.5 and r["position"] == 0
def test_requests_play_whole_in_order(d, player):
    a = d.speak("A one. " * 60)["id"]; b = d.speak("B one.")["id"]; d.wait_done(b, timeout=30)
    owners = [rid for rid, _ in player.played]; assert owners == sorted(owners, key=[a, b].index)
def test_stop_clears_everything(d, player):
    d.speak("x. " * 100); d.speak("y."); time.sleep(0.4)
    assert d.stop()["stopped"] == 2 and d.status()["queued"] == [] and d.status()["playing"] is None
def test_new_speak_does_not_interrupt(d, player):
    a = d.speak("first. " * 5)["id"]; time.sleep(0.2); d.speak("second.")
    d.wait_done(a, timeout=30); assert not player.was_stopped
def test_save_bypasses_queue(d, tmp_path):
    d.speak("long. " * 100); t = time.monotonic()
    r = d.save("Saved text.", str(tmp_path/"s.wav")); assert time.monotonic() - t < 5 and Path(r["path"]).exists()
def test_bad_voice_400(d):
    with pytest.raises(ValueError, match="Sofia"): d.speak("hi", voice="Bob")
def test_nothing_to_speak(d):
    with pytest.raises(ValueError, match="Nothing to speak"): d.speak("   ")
def test_second_daemon_exits_when_port_taken(running_daemon_port):
    assert subprocess.run([sys.executable, "-m", "magpie_voice", "daemon", "--port", str(running_daemon_port)], timeout=20).returncode == 0
def test_wait_done_survives_daemon_restart(d, restart_daemon):
    rid = d.speak("x.")["id"]; restart_daemon(); d.wait_done(rid, timeout=60)   # returns, no hang
def test_idle_shutdown():
    dm = Daemon(FakeEngine(), FakePlayer(), port=0, idle_timeout=0.5); th = threading.Thread(target=dm.serve_forever); th.start()
    th.join(5); assert not th.is_alive()
```

- [ ] **Step 2:** Run `uv run pytest tests/test_daemon.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `daemon.py`, `client.py` and the `daemon` entry in `__main__.py` (with a `--port` option) as in Interfaces. Log to `%LOCALAPPDATA%\MagpieVoice\daemon.log`.
- [ ] **Step 4:** Run `uv run pytest tests/test_daemon.py -v`. Expected: PASS.
- [ ] **Step 5:** Run a real check: `uv run python -c "from magpie_voice import client as c; c.speak('Hello from the shared queue. This is the second sentence.'); c.speak('And a second request waits its turn.')"`. Expected: both play in full, one after the other, and the first word comes within about 15 s on a cold start.
- [ ] **Step 6:** `git commit -m "feat: PC-wide speaker daemon with queue, stop, save"`

### Task 6: CLI

**Files:**
- Create: `src/magpie_voice/cli.py`
- Test: `tests/test_cli.py` (monkeypatch `magpie_voice.client` functions)

**Interfaces:**
- Consumes: `client.*`.
- Produces: `main(argv: list[str] | None = None) -> int`. The subcommands are exactly as in spec §9.3:
  - `say [TEXT|-] [--file F] [--voice] [--lang]` speaks, then calls `wait_done`. Ctrl+C calls `client.stop()` and returns 130.
  - `save [TEXT|-] [--file F] -o/--output PATH [--voice] [--lang] [--format wav|mp3] [--overwrite] [--raw]` prints the absolute path. `--raw` sends `clean=False`.
  - `voices` prints the voices and languages.
  - `gui` launches `gui.run()`.
  - `mcp` launches `mcp_server.run()`.
  - `daemon` behaves as in Task 5.
  - Errors print `error: <msg>` to stderr and return 2. Files are read as UTF-8.

- [ ] **Step 1: Write the failing tests:** `test_say_waits_for_done`, `test_say_reads_stdin_dash`, `test_save_prints_path`, `test_save_file_option_utf8` (a file containing `"Ünïcødé."`), `test_error_returns_2_with_message` (the client raises `ValueError("Unknown voice")`, then expect stderr to contain `error: Unknown voice` and the return code to be 2), and `test_no_text_given_errors`.
- [ ] **Step 2:** Run `uv run pytest tests/test_cli.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement with `argparse`. Import `gui` and `mcp_server` lazily inside their branches.
- [ ] **Step 4:** Run `uv run pytest tests/test_cli.py -v`. Expected: PASS. Then run `uv run magpie-voice save "Testing the command line." -o spike/cli-test.mp3`, which should print the path, and the file should play.
- [ ] **Step 5:** `git commit -m "feat: magpie-voice CLI"`

### Task 7: MCP server

**Files:**
- Create: `src/magpie_voice/mcp_server.py`
- Test: `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: `client.*`.
- Produces: `run() -> None` (FastMCP named `magpie-voice`, stdio). The tools are:
  - `speak(text: str, voice: str | None = None, language: str | None = None) -> str`, which returns `"Queued (position N, M sentences)."`
  - `stop() -> str`, which returns `"Stopped. Dropped N request(s)."`
  - `save_audio(text: str, path: str | None = None, voice: str | None = None, language: str | None = None, format: str | None = None, overwrite: bool = False) -> str`, which returns `"Saved <abs path> (<duration>s, <fmt>)."`
  - `list_voices() -> str`
  - Each tool docstring says what it does in one line. The `speak` docstring adds "returns immediately; audio plays in the background, queued behind other requests". `ValueError`/`RuntimeError` from the client turn into tool errors with the same message.

- [ ] **Step 1: Write the failing tests:** call the tool functions directly with a monkeypatched client.
  - `test_speak_message`
  - `test_save_message_has_path`
  - `test_error_passthrough`, where `ValueError("Unknown voice 'Bob'. Choose from: Aria, Jason, John, Leo, Sofia")` should surface unchanged
  - `test_tools_registered`, where the FastMCP tool list equals `{speak, stop, save_audio, list_voices}`
- [ ] **Step 2:** Run `uv run pytest tests/test_mcp_server.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement with `mcp.server.fastmcp.FastMCP`.
- [ ] **Step 4:** Run `uv run pytest tests/test_mcp_server.py -v`. Expected: PASS.
- [ ] **Step 5:** `git commit -m "feat: MCP server tools"`

### Task 8: Window (layout A)

**Files:**
- Create: `src/magpie_voice/gui.py`
- Test: `tests/test_gui.py` (logic only, so no display is needed)

**Interfaces:**
- Consumes: `client.*`, `config.load_settings`.
- Produces:
  - `run() -> None`.
  - `class App` (window title `Magpie Voice`, about 520×380, resizable). From top to bottom it has:
    - a multi-line `Text` box,
    - `Voice` and `Language` comboboxes (read-only, filled from `client.voices()`, defaults from settings),
    - the buttons `▶ Speak`, `■ Stop` and `💾 Save as…` (`asksaveasfilename`, with types WAV/MP3 and initial dir `settings.output_dir`),
    - a status label.
  - All client calls run on a worker thread and post results back with `after()`.
  - While speaking, the window polls `client.status()` every 500 ms and shows `progress`, `"Done"` or `"Saved <path>"`. Errors appear in the status line in red.
  - `App.on_speak/on_stop/on_save(path)` are callable from tests.

- [ ] **Step 1: Write the failing tests:** create `App` with `tk.Tk()` hidden (skip if `TclError`) and a monkeypatched client.
  - `test_speak_sends_text_voice_language`
  - `test_empty_text_shows_error_without_calling_client`
  - `test_save_reports_path_in_status`
- [ ] **Step 2:** Run `uv run pytest tests/test_gui.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement with `tkinter`/`ttk`.
- [ ] **Step 4:** Run `uv run pytest tests/test_gui.py -v`. Expected: PASS. Then run `uv run magpie-voice gui` by hand: Speak, then Stop part-way, then Save as… mp3.
- [ ] **Step 5:** `git commit -m "feat: Tkinter window"`

### Task 9: Skill, setup script, README

**Files:**
- Create: `skill/magpie-voice/SKILL.md`, `scripts/setup.ps1`, `README.md`

**Interfaces:**
- Consumes: everything above.
- `setup.ps1` is idempotent. Each step is skipped if it's already done:
  1. Download the engine zip v0.3.0 with `Invoke-WebRequest` from `https://github.com/NVIDIA/NeMo-Speech.cpp/releases/download/v0.3.0/nemo-speech-0.3.0-windows-x86_64-cpu.zip`, check SHA-256 `4ed9740e361e4653f56c3dce7d1e81883a1c8b831c1bd7d01567fff1130b5b05`, and unzip it to `vendor/nemo-speech/`.
  2. Run `nemo-speech pull magpie` with `NEMO_SPEECH_MODEL_DIR=models`.
  3. Run `uv sync`.
  4. Run `claude mcp add --scope user magpie-voice -- uv run --directory "<ROOT>" magpie-voice mcp`. Skip it if `claude mcp get magpie-voice` succeeds.
  5. Copy `skill/magpie-voice` to `$HOME\.claude\skills\magpie-voice`.
  6. Create a Start-menu shortcut "Magpie Voice" pointing to `<ROOT>\.venv\Scripts\pythonw.exe -m magpie_voice gui`.
  7. Print a summary.
- `SKILL.md` frontmatter:
  - `name: magpie-voice`.
  - The `description` triggers on: read aloud / say it / speak your answer / stop talking / save as audio, wav or mp3 / make a voice file or narration of text / choose a voice (Aria, Jason, John, Leo, Sofia).
  - It explicitly says **"Not for adding voice-over to /demo-video recordings — use /demo-voiceover for that."**
  - The body tells Claude to:
    - pass a short spoken version (no tables or code) to `speak`,
    - use `save_audio` with a descriptive file name when a file is wanted, and report the returned path,
    - use `stop` for "stop/quiet", and
    - use `list_voices` when unsure.

- [ ] **Step 1:** Write `SKILL.md`, `setup.ps1` and `README.md` (install, CLI usage, window, Claude usage, where files go, troubleshooting log paths).
- [ ] **Step 2:** Run `pwsh -File scripts/setup.ps1` twice. Expected: the first run completes, and the second reports every step as already done.
- [ ] **Step 3:** Run `claude mcp get magpie-voice`. Expected: it's listed and connected. Then check `Test-Path $HOME\.claude\skills\magpie-voice\SKILL.md`, which should return `True`.
- [ ] **Step 4:** Run the full suite: `uv run pytest -v`. Expected: everything passes, with engine tests included.
- [ ] **Step 5:** Run the manual checklist (spec §11) in a **new** Claude Code session:
  - "read this to me: …" (heard),
  - "save that as hello.mp3" (path returned, file plays),
  - two sessions speaking at once (they queue, no overlap),
  - "stop talking" (silence).
- [ ] **Step 6:** `git commit -m "feat: setup script, Claude skill, README"`
