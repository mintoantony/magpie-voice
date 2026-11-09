# Engine spike (2026-11-06)

**Result: keep NVIDIA NeMo-Speech.cpp.** It passes every check in the design (§6), so the fallback (mudler/magpie-tts.cpp) wasn't needed.

## Setup
- Engine: NeMo-Speech.cpp **v0.3.0**, `nemo-speech-0.3.0-windows-x86_64-cpu.zip` from GitHub releases.
  - SHA-256 `4ed9740e361e4653f56c3dce7d1e81883a1c8b831c1bd7d01567fff1130b5b05` (matches the published `.sha256`).
  - Unzipped to `vendor/nemo-speech/nemo-speech-0.3.0-windows-x86_64-cpu/`. The exe is `bin/nemo-speech.exe`. The MSVC runtime DLLs are bundled.
- Models: setting `NEMO_SPEECH_MODEL_DIR=<repo>/models` keeps the download inside the project folder (638 MB):
  - `magpie_tts_multilingual_357m.v2607.f16.gguf` (542 MB)
  - NanoCodec decoder f16 (75 MB)
  - tokenizer (30 MB)
  The first `synthesize` call downloads all of these automatically and checks their SHA-256 (it needs curl, which Windows ships). They can also be fetched ahead of time with `nemo-speech pull magpie`.
- PC: Intel Core Ultra 7 265HX (20 cores), 63 GB RAM, CPU only. `nemo-speech doctor` shows only `cpu`.

## Voices and languages (from `GET /v1/models`)
- Voices (names are case-insensitive): John, Sofia, Aria, Jason, Leo. All 5 were tested.
- Languages: en-US, es-ES, de-DE, fr-FR, it-IT, vi-VN, hi-IN, ar-AE, ar-SA, ar-MSA, ko-KR, pt-BR. es-US was also accepted by the CLI.
- Output: mono PCM16 at 22050 Hz.

## Speed
| Mode | Wall time | Audio |
|------|-----------|-------|
| CLI `synthesize`, one process per call (includes model load) | 4.33 s | ~3.3 s |
| `nemo-speech serve`, warm, request 1 | 3.20 s | 4.18 s |
| `nemo-speech serve`, warm, request 2 | 4.01 s | 6.69 s |

With the model kept loaded, the engine makes speech **faster than real time** (about 0.6–0.75 s of compute per 1 s of audio). → **Design consequence:** keep one long-running `nemo-speech serve` process and send it sentence-sized requests.

## HTTP API used
`nemo-speech serve --host 127.0.0.1 --port N --no-ui --tts-model magpie`

Then `POST /v1/audio/speech`:
- JSON body: `{"input": str, "voice": str, "language": "en-US", "response_format": "pcm"|"wav", "sample_rate"?: int}`.
- The server buffers the whole result before replying (no streaming).
- An unknown voice returns 400. `speed` must be 1.0.
- `GET /health` returns `{"status":"ok"}`.

Notes:
- Text normalization isn't available on Windows. Numbers and symbols are spoken as the model guesses them, so the Python clean-up step matters.
- The serve process starts answering `/health` straight away. The first speech request may be slower while it warms up.
