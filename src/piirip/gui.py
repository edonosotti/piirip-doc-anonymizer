"""Minimal desktop GUI: drop or pick a document, then choose where to save the redacted copy."""
from __future__ import annotations

import queue
import shutil
import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .handlers import HANDLERS

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:  # drag and drop is optional; clicking still works
    DND_FILES = None
    TkinterDnD = None


def redact_file(src: Path, dst: Path, redactor) -> int:
    """Redact `src` into `dst` and return the number of redactions."""
    before = redactor.count
    HANDLERS[src.suffix.lower()](src, dst, redactor)
    return redactor.count - before


class App:
    def __init__(self) -> None:
        self.root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
        self.root.title(f"PII-rip {__version__}")
        self.root.geometry("460x260")
        self.root.minsize(360, 200)
        self.redactor = None
        self.busy = False
        self.results: queue.Queue = queue.Queue()

        exts = " ".join(sorted(HANDLERS))
        hint = "Drop a document here\nor click to choose one" if DND_FILES else "Click to choose a document"
        self.zone = tk.Label(
            self.root, text=f"{hint}\n\n{exts}", relief="groove", borderwidth=3,
            cursor="hand2", justify="center", padx=10, pady=10,
        )
        self.zone.pack(fill="both", expand=True, padx=12, pady=(12, 6))
        self.zone.bind("<Button-1>", lambda _e: self.choose())
        if DND_FILES:
            self.zone.drop_target_register(DND_FILES)
            self.zone.dnd_bind("<<Drop>>", self.on_drop)

        self.bar = ttk.Progressbar(self.root, mode="indeterminate")
        self.status = tk.StringVar(value="Ready")
        self.status_label = tk.Label(self.root, textvariable=self.status, anchor="w")
        self.status_label.pack(fill="x", padx=12, pady=(0, 8))
        self.root.after(100, self.poll)

    def choose(self) -> None:
        if self.busy:
            return
        patterns = " ".join(f"*{e}" for e in sorted(HANDLERS))
        path = filedialog.askopenfilename(
            title="Select a document", filetypes=[("Supported documents", patterns), ("All files", "*.*")]
        )
        if path:
            self.start(Path(path))

    def on_drop(self, event) -> None:
        paths = self.root.tk.splitlist(event.data)
        if self.busy or not paths:
            return
        if len(paths) > 1:
            messagebox.showwarning("PII-rip", "Please drop one file at a time.")
            return
        self.start(Path(paths[0]))

    def start(self, src: Path) -> None:
        if not src.is_file() or src.suffix.lower() not in HANDLERS:
            messagebox.showerror("PII-rip", f"Unsupported file: {src.name}\nSupported: {' '.join(sorted(HANDLERS))}")
            return
        self.busy = True
        self.bar.pack(fill="x", padx=12, before=self.status_label)
        self.bar.start(12)
        self.status.set(f"Processing {src.name} (the first run loads the language model)...")
        threading.Thread(target=self.work, args=(src,), daemon=True).start()

    def work(self, src: Path) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="piirip-"))
        try:
            if self.redactor is None:
                from .engine import Redactor
                from .playbooks import load_playbook

                self.redactor = Redactor(load_playbook("default"))
            out = tmp / f"{src.stem}.redacted{src.suffix}"
            count = redact_file(src, out, self.redactor)
            self.results.put(("ok", src, out, tmp, count))
        except Exception as e:  # noqa: BLE001
            shutil.rmtree(tmp, ignore_errors=True)
            self.results.put(("error", src, str(e)))

    def poll(self) -> None:
        try:
            msg = self.results.get_nowait()
        except queue.Empty:
            self.root.after(100, self.poll)
            return
        self.bar.stop()
        self.bar.pack_forget()
        self.busy = False
        if msg[0] == "error":
            self.status.set("Failed")
            messagebox.showerror("PII-rip", f"Could not process {msg[1].name}:\n{msg[2]}")
        else:
            _, src, out, tmp, count = msg
            try:
                self.save(src, out, count)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        self.root.after(100, self.poll)

    def save(self, src: Path, out: Path, count: int) -> None:
        ext = src.suffix
        target = filedialog.asksaveasfilename(
            title=f"Save redacted copy ({count} redactions)",
            initialdir=str(src.parent),
            initialfile=out.name,
            defaultextension=ext,
            filetypes=[(f"{ext} files", f"*{ext}")],
        )
        if not target:
            self.status.set("Cancelled, nothing saved")
            return
        try:
            shutil.copyfile(out, target)
        except OSError as e:
            self.status.set("Failed")
            messagebox.showerror("PII-rip", f"Could not save the file:\n{e}")
            return
        self.status.set(f"Saved {Path(target).name} ({count} redactions)")

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    App().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
