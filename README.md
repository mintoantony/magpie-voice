# Magpie Voice

Local, offline text-to-speech for this Windows PC using **NVIDIA Magpie TTS Multilingual 357M**. It runs on the CPU through NVIDIA's C++/GGUF runtime **NeMo-Speech.cpp**, so it needs no NeMo, PyTorch or GPU.

There are three ways to use it:
- **Claude Code**, through an MCP server and the `magpie-voice` skill
- a **command line**
- a **small window**

## Setup (once)

```powershell
pwsh -File scripts\setup.ps1
```

The script:
- downloads the engine and checks its SHA-256,
- downloads the model (about 650 MB) into `models\`,
- runs `uv sync`,
- registers the MCP server with Claude Code (user scope),
- installs the skill to `~\.claude\skills\magpie-voice\`, and
- adds a **Magpie Voice** Start-menu shortcut.

You can run it again at any time. Steps that are already done are skipped. You need `uv` and the `claude` CLI on PATH.

## Command line

```powershell
uv run magpie-voice say "Hello there"                    # read aloud (Ctrl+C stops)
uv run magpie-voice say "Hola" --voice Sofia --lang es
uv run magpie-voice say --file notes.txt
uv run magpie-voice save "Hello there" -o hello.wav
uv run magpie-voice save --file script.txt -o narration.mp3 --voice Jason
uv run magpie-voice stop                                 # silence everything
uv run magpie-voice voices                               # list voices and languages
uv run magpie-voice gui                                  # open the window
```

- `save` options:
  - `--format wav|mp3`
  - `--overwrite` to replace an existing file
  - `--raw` to keep Markdown and symbols as they are
- Relative paths, and saves with no `-o`, go to `Documents\MagpieVoice\`.

## Window

Open it from the Start menu (**Magpie Voice**) or with `uv run magpie-voice gui`. Paste text, choose a voice and language, then press **Speak**, **Stop** or **Save as…**.

## Claude Code

Open a new Claude Code session after setup, then ask, for example:
- "read that to me",
- "say it in Sofia's voice",
- "save this paragraph as intro.mp3",
- "stop talking".

The MCP tools are `speak`, `stop`, `save_audio` and `list_voices`.

## How it works

```
Claude (MCP) ─┐
CLI ──────────┼─► speaker daemon 127.0.0.1:47391 ─► nemo-speech serve 127.0.0.1:47390
Window ───────┘     (one queue for the whole PC)        (Magpie model kept loaded)
```

- The first client that needs the daemon starts it. The daemon closes itself, and the engine with it, after 30 minutes idle.
- Read-aloud requests from every Claude session, the CLI and the window share one queue, so they never talk over each other.
- **Stop** clears everything.
- Saving files doesn't wait in that queue.
- Text is cleaned before speaking:
  - Markdown is removed,
  - code blocks are skipped,
  - URLs are dropped, and
  - `% & $ °` are spelled out in English.

## Voices and languages

- **Voices:** Aria (default), Jason, John, Leo, Sofia.
- **Languages:** en-US (default), es-ES, de-DE, fr-FR, it-IT, pt-BR, hi-IN, ko-KR, vi-VN, ar-MSA, ar-AE and ar-SA. Short codes such as `en`, `es` and `pt` also work.

To change the defaults, create `%APPDATA%\MagpieVoice\config.toml`:

```toml
voice = "Sofia"
language = "en-US"
output_dir = "D:/Audio/Magpie"
```

## Troubleshooting

- The logs are in `%LOCALAPPDATA%\MagpieVoice\`: `daemon.log` and `engine.log`.
- On CPU expect about 9 s before the first word on a cold start, then faster than real time while the model stays loaded.
- To run the tests, use `uv run pytest`. Add `-m "not engine"` to skip the tests that need the real engine.

## Licences

- Engine: NeMo-Speech.cpp (Apache-2.0).
- Model and codec: NVIDIA Open Model License.
