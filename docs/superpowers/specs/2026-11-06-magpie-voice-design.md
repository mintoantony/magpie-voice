# Magpie Voice: design

Date: 2026-11-06
Status: draft, awaiting the owner's approval

## 1. Intent

The owner wants a local text-to-speech app on their own Windows PC that Claude can use. Claude should be able to:

- **read text out loud** on the PC's speakers, for example "read this reply to me", and
- **save speech as audio files** to use later, for example narration for a demo video.

The owner also wants to use the app **without Claude**, from a **command line** and from a **small window**.

The voice engine must be **NVIDIA Magpie TTS Multilingual 357M**, run through a **GGUF / C++ runtime, not the full NeMo/PyTorch stack**. The app must be **standalone**: once it's set up, it runs from its own folder with no other services, works offline after the first model download, and needs no extra setup each time.

The language is Python where possible. It covers the app logic, the MCP server, the CLI and the window. The C++ engine is used as a ready-made dependency.

## 2. Goals

1. One shared Python core, used by all three ways in (MCP, CLI, window), so a voice sounds the same everywhere.
2. **MCP server** (stdio) that Claude Code can call, plus a **Claude skill** that tells Claude when and how to use it.
3. **CLI** called `magpie-voice`.
4. **Small window** (layout A, below).
5. Read aloud with the shortest practical wait on **CPU only**.
6. Save audio as WAV, and as MP3 on request.

## 3. Non-goals

- Running on a GPU. The PC has no NVIDIA GPU, so the design is CPU-only. Supporting GPU later shouldn't be blocked, but it isn't built now.
- Sharing with teammates, building an installer, or packaging for other PCs. It's **just the owner's PC for now**.
- Voice cloning. It was removed from this model release anyway.
- Speech-to-text, or any cloud TTS service.
- Mandarin and Japanese, unless the chosen engine turns out to support them.

## 4. Anti-goals (failures even if it "works")

- Pulling in NeMo, PyTorch or CUDA. That defeats the point of the GGUF/C++ choice.
- Claude being blocked while audio plays. A `speak` call must return straight away.
- Reading Markdown symbols, code blocks or URLs out loud word for word ("asterisk asterisk…").
- A new request **cutting off** speech that's already playing. New text waits in a queue; only Stop clears it.
- Needing a terminal or a manual "start the server" step before Claude can use it.

## 5. The PC (checked on 2026-11-06)

- Windows 11 Enterprise, Intel Core Ultra 7 265HX (20 cores), 63 GB RAM, **no NVIDIA GPU**.
- Python 3.14 and `uv` 0.11 are installed. ffmpeg is **not** installed. No TTS engine is installed yet.
- Project folder: `D:\VanguardProjects\Agents\Text2Voice` (empty, not a git repo yet).

## 6. Engine (decided with the owner; details checked on the web 2026-11-06)

**Primary: NVIDIA NeMo-Speech.cpp** (https://github.com/NVIDIA/NeMo-Speech.cpp, Apache-2.0). It's NVIDIA's own ggml-based C++ runtime and runs Magpie 357M from GGUF.
- It has prebuilt Windows zips, `nemo-speech-<version>-windows-<arch>-<backend>.zip`, including a CPU backend.
- The CLI is `nemo-speech synthesize "text" --output speech.wav`, and `nemo-speech pull magpie` downloads the model, tokenizer and NanoCodec.
- It also offers a C API (`include/nemo_speech/tts.h`, PCM16 chunks through a callback) and an HTTP API/server.
- Its docs say text normalization isn't supported on Windows. This is one reason for the Python text clean-up in §8.

**Fallback: mudler/magpie-tts.cpp** (https://github.com/mudler/magpie-tts.cpp, MIT). Use it only if NeMo-Speech.cpp's Windows CPU build can't do TTS or doesn't work.
- There are no prebuilt binaries, so it has to be built with CMake and Visual Studio Build Tools.
- GGUFs are at https://huggingface.co/mudler/magpie-tts.cpp-gguf (`magpie-tts-multilingual-357m-q8_0.gguf` is recommended).
- The CLI is `magpie-cli say --model … --text … --lang en --speaker Aria --output out.wav`.
- The C ABI (`magpie_tts_capi.h`) returns float32 PCM at 22,050 Hz.

**Model facts:**
- Voices: Aria, Jason, John, Leo, Sofia.
- Languages: about 10, including en, es, de, fr, it, pt-BR, hi, vi, ko and ar.
- Output is 22.05 kHz mono, and one call produces at most about 20 seconds of audio.
- Licence: NVIDIA Open Model License, which allows commercial use.

**Expected speed:** mudler's benchmark is about 2.6 s of compute per 1 s of speech on a fast desktop CPU (q8_0). Expect a wait of a few seconds before the first word.

**The engine sits behind one Python interface** (`Engine.synthesize(text, voice, language) -> (pcm, sample_rate)`), so the backend can be swapped without touching anything else.

**Left to the builder:** how Python talks to the engine. The options are a subprocess per call, a long-running engine server process, or the C API through `ctypes`. Prefer whatever keeps the model loaded between sentences, if the engine allows it. Measure before choosing.

**First task, a spike:**
1. Install the NeMo-Speech.cpp Windows CPU build into the app folder.
2. Pull the model.
3. Synthesize one English sentence and one non-English sentence.
4. Time it, and record the voice and language names the CLI actually accepts.

**How to decide after the spike (my call):**
- **Keep NeMo-Speech.cpp** if it runs on CPU on this PC, accepts all 5 voices and at least English, and is no more than about 30% slower than mudler/magpie-tts.cpp on the same sentence.
- **Switch to the fallback** if NeMo-Speech.cpp fails any of those checks.
- Measuring the fallback for the comparison means building it. If Visual Studio Build Tools aren't installed, keep NeMo-Speech.cpp as long as it passes the other checks and runs at no more than about 3 s of compute per 1 s of speech.
- Record the numbers in `docs/engine-spike.md`.

## 7. Installation layout (my call; the owner only said "just my PC")

Everything lives in the project folder:

```
Text2Voice/
  pyproject.toml            # uv project; console script "magpie-voice"
  src/magpie_voice/         # Python package
  vendor/nemo-speech/       # unzipped engine binaries (not global PATH)
  models/                   # downloaded GGUF + assets
  scripts/setup.ps1         # one-time: fetch engine + model, uv sync, register MCP, install skill
  docs/
  tests/
```

- `scripts/setup.ps1` is the single setup step. It downloads the engine zip and checks its SHA-256, pulls the model, runs `uv sync`, registers the MCP server with Claude Code (user scope), and copies the skill to `~/.claude/skills/magpie-voice/`.
- After setup, nothing has to run in the background. Claude Code starts the MCP server itself when needed.
- The engine and model are referenced by path inside the folder. The global PATH is never changed.

## 8. Shared core (Python)

- **Text clean-up before speaking (my call):**
  - Strip Markdown: headings, bold, bullets and links (keep the link text).
  - Replace code blocks with a short spoken note such as "code block skipped". Drop bare URLs.
  - Expand a few common symbols ("&", "%", "°", and "$" with numbers) for English.
  - This applies to read-aloud and to saved files, with an option to turn it off for files.
- **Chunking:** split text into sentences, and merge short ones, so each engine call stays well under the ~20 s limit.
- **Read aloud as a pipeline:** produce sentence 1 → start playing it → produce sentence 2 in the background while 1 plays → and so on.
  - New `speak` requests join the end of the **PC-wide** queue (§10).
  - **Stop** clears the queue and cuts off the current audio.
- **Save:** produce every chunk and join them with a short pause (about 250 ms) between sentences.
  - Write a WAV file at 22.05 kHz mono, 16-bit.
  - Write MP3 only when the file name ends in `.mp3` or the format is asked for. Use a pip-installable encoder (for example `lameenc`) so ffmpeg isn't needed. The builder checks that a wheel exists for the Python version used, and may pin Python 3.12/3.13 in the uv project if 3.14 wheels are missing.
- **Default output folder:** `%USERPROFILE%\Documents\MagpieVoice\`. Files get a timestamped name when only a folder, or nothing, is given. Existing files are never silently overwritten unless overwrite is asked for.
- **Defaults:** voice Aria and language English. These can be changed in a small settings file (`%APPDATA%\MagpieVoice\config.toml` or similar), which all three ways in read.
- **Playback:** through the default Windows audio device (for example with `sounddevice`). The library choice is left to the builder.

## 9. The three ways in

### 9.1 MCP server (stdio, Python `mcp` SDK / FastMCP)

Tools:

| Tool | Does | Returns |
|------|------|---------|
| `speak(text, voice?, language?)` | Queues text to be read aloud | Straight away: `"queued"`, plus a rough length in seconds |
| `stop()` | Stops playback and clears the queue | `"stopped"` |
| `save_audio(text, path?, voice?, language?, format?)` | Makes the whole file and **waits until it is written** | The absolute path, duration and format |
| `list_voices()` | Lists voices and languages | A list |

- Errors (bad voice, engine missing, path not writable) come back as plain-language tool errors that Claude can pass on to the owner.
- `save_audio` may take a while for long text on CPU. That's acceptable, because the owner asked for a file and expects to wait.
- Registration: `claude mcp add --scope user magpie-voice -- uv run --directory D:\VanguardProjects\Agents\Text2Voice magpie-voice mcp` (exact form left to the builder).

### 9.2 Claude skill (`~/.claude/skills/magpie-voice/SKILL.md`)

- It triggers on requests like "read this to me", "say it out loud", "speak your answer", "make a voice-over/narration/audio file of…", "save this as mp3", "use Sofia's voice" and "stop talking".
- **Keep separate from the owner's existing `/demo-voiceover` skill (decided by the owner).** Magpie Voice doesn't replace it or feed it for now. This skill's description must say it is **not** for narrating `/demo-video` recordings, so requests like "add a voice-over to the demo video" still go to `/demo-voiceover`. Standalone files ("save this paragraph as narration.mp3") belong to this skill.
- It tells Claude to:
  - pass the **spoken** version of the text (short, no tables or code),
  - use `save_audio` with a sensible file name when a file is wanted,
  - report the saved path back to the owner, and
  - call `stop` when asked.

### 9.3 CLI (`magpie-voice`)

```
magpie-voice say "Hello there" [--voice Sofia] [--lang en]
magpie-voice say --file notes.txt
magpie-voice save "Hello there" -o hello.wav [--voice …] [--lang …]
magpie-voice save --file script.txt -o narration.mp3
magpie-voice voices
magpie-voice gui
magpie-voice mcp           # used by Claude Code; not for humans
```

- `say` blocks until playback ends, and Ctrl+C stops it.
- `save` prints the output path.
- `say -` and `save -` read from stdin (my call).

### 9.4 Window (layout A, chosen by the owner)

- One window: a multi-line text box, then **Voice** and **Language** drop-downs, then **▶ Speak**, **■ Stop** and **💾 Save as…**, and a status line underneath (for example "Making sentence 2 of 5…" or "Saved C:\…\hello.wav").
- Built with Tkinter from the standard library (my call), so there's no extra GUI dependency.
- Synthesis runs off the UI thread, so the window never freezes.
- Starting it: `magpie-voice gui`, plus a desktop/Start-menu shortcut created by setup (my call).

## 10. One shared speech queue for the whole PC (decided by the owner)

The owner often runs several Claude sessions at once, and each one starts its own MCP server process. The window and the CLI are separate processes too. **The owner decided that all of them share one queue on the PC**, so audio never overlaps.

- Read-aloud requests from any process join **one first-come, first-served queue**.
- A request plays **whole**. Sentences from two requests are never mixed together.
- Producing the audio for a waiting request may start early, but playing it waits its turn.
- **Stop** (from Claude, the window or Ctrl+C in the CLI) stops what's playing now and clears **every** waiting request, whichever process sent it (my call: "stop talking" should mean silence).
- `speak` still returns to Claude straight away, even when its request is waiting behind others.
- Saving files (`save_audio`, `save`, Save as…) does **not** use the queue. It plays nothing, so it can run alongside.
- The mechanism is left to the builder. One option is a small shared "speaker" background process that the first caller starts and that quits after some idle time, reached over a local named pipe or localhost port. Another is a machine-wide lock with a stop signal. The result has to be simple to set up: still no manual start step, and nothing for the owner to run first.
- If a process crashes while it holds the queue, the queue must not stay stuck.

## 11. Testing (left mostly to the builder)

- Unit tests for text clean-up, chunking, file naming and WAV/MP3 writing, using a fake engine.
- A small number of real-engine tests: one short sentence per voice, checking that audio comes out and has a sensible length. Mark them so they can be skipped when the engine isn't installed.
- A manual check list: Claude reads a reply aloud, Claude saves an mp3, the window's Speak/Stop/Save, and the CLI's `say` and `save`.

## 12. Calls I made (please check)

- NeMo-Speech.cpp is the primary engine and mudler/magpie-tts.cpp the fallback (the owner leaned this way after the research, but didn't explicitly confirm).
- Everything lives in the project folder, with one `setup.ps1`. The engine isn't added to the global PATH.
- Markdown and code are stripped before speaking.
- New `speak` calls are queued, not interrupting.
- Files go to `Documents\MagpieVoice\` by default. WAV is the default and MP3 is produced without ffmpeg.
- The window uses Tkinter. Setup creates a shortcut.
- Stop clears every waiting request on the PC, not just the caller's own.
- How to judge the engine spike (the 30% / 3 s limits in §6).
