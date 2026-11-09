"""Small Tkinter window: paste text, pick a voice, Speak / Stop / Save as."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import filedialog, ttk

from . import config

try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


class App:
    def __init__(self, root: tk.Tk, client=None, background: bool = True) -> None:
        if client is None:
            from . import client as default_client
            client = default_client
        self.root = root
        self.client = client
        self.background = background
        self.settings = config.load_settings()
        self._watching: str | None = None

        root.title("Magpie Voice")
        root.geometry("560x400")
        root.minsize(420, 300)

        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="both", expand=True)

        self.text = tk.Text(frame, wrap="word", height=10, font=("Segoe UI", 11), undo=True)
        self.text.pack(fill="both", expand=True)

        row = ttk.Frame(frame)
        row.pack(fill="x", pady=(10, 0))
        ttk.Label(row, text="Voice").pack(side="left")
        self.voice = ttk.Combobox(row, values=list(config.VOICES), state="readonly", width=10)
        self.voice.set(self.settings.voice)
        self.voice.pack(side="left", padx=(6, 16))
        ttk.Label(row, text="Language").pack(side="left")
        self.language = ttk.Combobox(row, values=list(config.LANGUAGES), state="readonly", width=10)
        self.language.set(self.settings.language)
        self.language.pack(side="left", padx=6)

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="▶ Speak", command=self.on_speak).pack(side="left")
        ttk.Button(buttons, text="■ Stop", command=self.on_stop).pack(side="left", padx=8)
        ttk.Button(buttons, text="💾 Save as…", command=self._ask_save).pack(side="left")

        self.status_var = tk.StringVar(value="Ready")
        self.status = ttk.Label(frame, textvariable=self.status_var, foreground="#444")
        self.status.pack(fill="x", pady=(10, 0))

        # Start the daemon (and warm the engine) while the user types.
        self._run(lambda: self.client.voices(), lambda _: None, quiet=True)

    # -- helpers -------------------------------------------------------------
    def _set_status(self, msg: str, error: bool = False) -> None:
        self.status_var.set(msg)
        self.status.configure(foreground="#b00020" if error else "#444")

    def _run(self, work, done, quiet: bool = False) -> None:
        def finish(result=None, err: Exception | None = None):
            if err is not None:
                if not quiet:
                    self._set_status(str(err), error=True)
            else:
                done(result)

        if not self.background:
            try:
                finish(work())
            except Exception as e:  # noqa: BLE001 - shown to the user
                finish(err=e)
            return

        def worker():
            try:
                result = work()
                self.root.after(0, lambda: finish(result))
            except Exception as e:  # noqa: BLE001
                self.root.after(0, lambda e=e: finish(err=e))

        threading.Thread(target=worker, daemon=True).start()

    def _content(self) -> str | None:
        content = self.text.get("1.0", "end").strip()
        if not content:
            self._set_status("Type or paste some text first.", error=True)
            return None
        return content

    # -- actions -------------------------------------------------------------
    def on_speak(self) -> None:
        content = self._content()
        if content is None:
            return
        voice, lang = self.voice.get(), self.language.get()
        self._set_status("Preparing speech…")

        def done(r):
            ahead = f" (waiting behind {r['position']})" if r["position"] else ""
            self._set_status(f"Queued {r['chunks']} sentence(s){ahead}")
            self._watching = r["id"]
            if self.background:
                self.root.after(500, self._poll)

        self._run(lambda: self.client.speak(content, voice, lang), done)

    def _poll(self) -> None:
        rid = self._watching
        if rid is None:
            return

        def done(s):
            if self._watching != rid:
                return
            if s["playing"] == rid:
                self._set_status(f"Speaking {s['progress']}")
            elif rid in s["queued"]:
                self._set_status("Waiting for other speech to finish…")
            else:
                self._set_status("Done")
                self._watching = None
                return
            self.root.after(500, self._poll)

        self._run(self.client.status, done)

    def on_stop(self) -> None:
        self._watching = None
        self._run(self.client.stop, lambda r: self._set_status("Stopped"))

    def _ask_save(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Save speech as",
            initialdir=str(self.settings.output_dir), defaultextension=".wav",
            filetypes=[("WAV audio", "*.wav"), ("MP3 audio", "*.mp3")])
        if path:
            self.on_save(path)

    def on_save(self, path: str) -> None:
        content = self._content()
        if content is None:
            return
        voice, lang = self.voice.get(), self.language.get()
        self._set_status("Making audio file… (this can take a while on CPU)")
        # The save dialog already asked before replacing an existing file.
        self._run(lambda: self.client.save(content, path, voice, lang, None, True),
                  lambda r: self._set_status(f"Saved {r['path']}"))


def run() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()
