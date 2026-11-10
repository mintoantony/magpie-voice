---
name: magpie-voice
description: Reads text aloud on this PC's speakers, or saves speech as a WAV or MP3 file, using the local offline Magpie Voice app (NVIDIA Magpie TTS). Use when the user asks to read something out loud, say it, speak your answer, read this to me, stop talking or be quiet, save text as audio, wav or mp3, make a voice file or spoken narration of some text, or use a particular voice (Aria, Jason, John, Leo, Sofia). Not for adding a voice-over to /demo-video recordings or making mp4s with sound; use /demo-voiceover for that.
---

# magpie-voice

The `magpie-voice` MCP server gives you four tools. They run offline on this PC.

| Tool | Use it for |
|---|---|
| `speak(text, voice?, language?)` | Reading text aloud. It returns at once, and the audio plays in the background. |
| `save_audio(text, path?, voice?, language?, format?, overwrite?)` | Writing a `.wav` or `.mp3` file. It waits until the file is written. |
| `stop()` | "stop", "quiet", "shut up", "that's enough". It silences everything. |
| `list_voices()` | When you're unsure which voices or languages exist. |

## Reading aloud

- Pass the **spoken version** of what you want to say, not your chat Markdown.
  - Use short, plain sentences.
  - Leave out tables, code, file paths and long URLs. Summarise them in words instead, for example "I changed three files".
  - Spell out what's awkward to hear.
- For "read your answer to me", give the answer in chat as usual, then `speak` a short spoken version of it.
- Speech from other Claude sessions shares one queue on this PC. Your request may wait its turn. That's expected, so don't call `stop` to jump the queue.
- The first word can take a few seconds, longer on a cold start. Don't call `speak` again because of that.

## Saving files

- Pick a short, descriptive file name, for example `intro-narration.mp3`.
  - A relative path goes under `Documents\MagpieVoice\`.
  - The extension chooses the format, and `.wav` is the default.
- Don't overwrite an existing file unless the user asks. If the tool says the file exists, ask the user, or choose a new name.
- Always tell the user the full path the tool returns.
- Long text takes a while on CPU, roughly a little under real time. Warn the user before saving anything longer than a few paragraphs.

## Voices and languages

- Voices: Aria (the default), Jason, John, Leo, Sofia.
- Languages: en, es, de, fr, it, pt (pt-BR), hi, ko, vi, ar (plus ar-AE, ar-SA). English is the default.
- Pass `language` whenever the text isn't English.

## If a tool fails

- Pass the error message on to the user in plain words.
- If the speech engine or daemon won't start, the logs are in `%LOCALAPPDATA%\MagpieVoice\` (`daemon.log`, `engine.log`). Setup is `scripts\setup.ps1` in `D:\VanguardProjects\Agents\Text2Voice`.
