"""Settings window (tkinter): sliders with live preview, Save / Cancel.

Runs in its own thread with its own Tk mainloop (the main thread belongs to
GLFW). All Tk calls stay on that thread; it talks to the app only through the
thread-safe App methods. Only one window exists at a time: asking again just
brings it to the front.
"""

from __future__ import annotations

import copy
import logging
import threading

from ginga.app import App
from ginga.config import Config
from ginga.settings import FIELDS, Field, format_value, get_value, offsets_summary, with_value

log = logging.getLogger(__name__)

PREVIEW_DELAY_MS = 80    # debounce slider drags before touching the renderer
POLL_MS = 250            # bring-to-front requests and offsets label refresh

SECTIONS = (("Animação", "wave"), ("Desempenho", "render"))

_lock = threading.Lock()
_thread: threading.Thread | None = None
_focus = threading.Event()


def open_settings(app: App) -> None:
    """Show the settings window, or bring it to the front if already open."""
    global _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            _focus.set()
            return
        _thread = threading.Thread(target=_run, args=(app,), name="settings", daemon=True)
        _thread.start()


def _run(app: App) -> None:
    try:
        SettingsWindow(app).mainloop()
    except Exception:
        log.exception("Settings window crashed")


class SettingsWindow:
    def __init__(self, app: App):
        import tkinter as tk
        from tkinter import ttk

        self.app = app
        self.original = copy.deepcopy(app.config)
        self.working = copy.deepcopy(app.config)
        self._preview_job = None
        self._values: dict[str, tk.DoubleVar] = {}
        self._labels: dict[str, ttk.Label] = {}

        root = self.root = tk.Tk()
        root.title("ginga wallpaper — Configurações")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.cancel)
        self._set_icon()
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Section.TLabel", font=("Segoe UI Semibold", 11))
        style.configure("Hint.TLabel", foreground="#6b6b6b", font=("Segoe UI", 8))

        body = ttk.Frame(root, padding=(20, 16, 20, 8))
        body.grid(sticky="nsew")
        row = 0
        for title, section in SECTIONS:
            ttk.Label(body, text=title, style="Section.TLabel").grid(
                row=row, column=0, columnspan=3, sticky="w", pady=(8 if row else 0, 4)
            )
            row += 1
            for f in (f for f in FIELDS if f.section == section):
                row = self._slider(body, f, row)
        self._pause_var = tk.BooleanVar(value=self.working.render.pause_when_fullscreen)
        ttk.Checkbutton(
            body,
            text="Pausar quando um jogo ou vídeo estiver em tela cheia",
            variable=self._pause_var,
            command=self._on_pause_toggle,
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(4, 0))
        row += 1

        ttk.Label(body, text="Monitores", style="Section.TLabel").grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(14, 4)
        )
        row += 1
        self._offsets = ttk.Label(body, text=offsets_summary(app.config.offsets))
        self._offsets.grid(row=row, column=0, columnspan=2, sticky="w")
        ttk.Button(body, text="Alinhar monitores…", command=app.request_calibrate).grid(
            row=row, column=2, sticky="e"
        )
        row += 1
        ttk.Label(
            body,
            text="Use quando os monitores estão desnivelados na mesa: a imagem passa contínua de um para o outro.",
            style="Hint.TLabel",
            wraplength=460,
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(2, 0))

        buttons = ttk.Frame(root, padding=(20, 8, 20, 16))
        buttons.grid(row=1, sticky="ew")
        buttons.columnconfigure(1, weight=1)
        ttk.Button(buttons, text="Restaurar padrões", command=self.reset).grid(row=0, column=0)
        ttk.Button(buttons, text="Cancelar", command=self.cancel).grid(row=0, column=2, padx=(0, 8))
        save = ttk.Button(buttons, text="Salvar", command=self.save, default="active")
        save.grid(row=0, column=3)
        root.bind("<Return>", lambda _e: self.save())
        root.bind("<Escape>", lambda _e: self.cancel())

        self._poll_job = root.after(POLL_MS, self._poll)
        root.lift()
        root.attributes("-topmost", True)
        root.after(300, lambda: root.attributes("-topmost", False))
        root.focus_force()

    # -- widgets ------------------------------------------------------------------------

    def _slider(self, parent, f: Field, row: int) -> int:
        import tkinter as tk
        from tkinter import ttk

        value = get_value(self.working, f)
        var = tk.DoubleVar(value=value)
        self._values[f.key] = var
        ttk.Label(parent, text=f.label).grid(row=row, column=0, sticky="w", padx=(0, 16))
        ttk.Scale(
            parent, from_=f.minimum, to=f.maximum, variable=var, length=280,
            command=lambda v, f=f: self._on_slide(f, float(v)),
        ).grid(row=row, column=1, sticky="ew")
        label = ttk.Label(parent, text=format_value(f, value), width=6, anchor="e")
        label.grid(row=row, column=2, sticky="e")
        self._labels[f.key] = label
        ttk.Label(parent, text=f.hint, style="Hint.TLabel").grid(
            row=row + 1, column=0, columnspan=3, sticky="w", pady=(0, 6)
        )
        return row + 2

    def _set_icon(self) -> None:
        try:
            from PIL import ImageTk

            from ginga.tray import icon_image

            self._icon = ImageTk.PhotoImage(icon_image(), master=self.root)
            self.root.iconphoto(True, self._icon)
        except Exception:
            log.debug("Could not set the settings window icon", exc_info=True)

    def _refresh_widgets(self) -> None:
        for f in FIELDS:
            value = get_value(self.working, f)
            self._values[f.key].set(value)
            self._labels[f.key].configure(text=format_value(f, value))
        self._pause_var.set(self.working.render.pause_when_fullscreen)

    # -- events -------------------------------------------------------------------------

    def _on_slide(self, f: Field, raw: float) -> None:
        self.working = with_value(self.working, f, raw)
        self._labels[f.key].configure(text=format_value(f, get_value(self.working, f)))
        self._schedule_preview()

    def _on_pause_toggle(self) -> None:
        self.working.render.pause_when_fullscreen = bool(self._pause_var.get())
        self._schedule_preview()

    def _schedule_preview(self) -> None:
        if self._preview_job is not None:
            self.root.after_cancel(self._preview_job)
        self._preview_job = self.root.after(PREVIEW_DELAY_MS, self._preview)

    def _preview(self) -> None:
        self._preview_job = None
        self.app.update_settings(self.working, persist=False)

    def reset(self) -> None:
        self.working = Config()
        self._refresh_widgets()
        self._schedule_preview()

    def save(self) -> None:
        self.app.update_settings(self.working, persist=True)
        self._close()

    def cancel(self) -> None:
        self.app.update_settings(self.original, persist=False)  # undo previews
        self._close()

    def _close(self) -> None:
        for job in (self._poll_job, self._preview_job):
            if job is not None:
                self.root.after_cancel(job)  # no callbacks into a dead window
        self.root.destroy()

    def _poll(self) -> None:
        if _focus.is_set():
            _focus.clear()
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        self._offsets.configure(text=offsets_summary(self.app.config.offsets))
        self._poll_job = self.root.after(POLL_MS, self._poll)

    def mainloop(self) -> None:
        self.root.mainloop()
