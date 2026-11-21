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
from pathlib import Path

from ginga.app import App
from ginga.config import Config
from ginga.settings import (
    FIELDS,
    FIT_LABELS,
    MEDIA_FILETYPES,
    TOGGLES,
    Field,
    Toggle,
    format_value,
    get_toggle,
    get_value,
    media_problem,
    offsets_summary,
    with_background,
    with_toggle,
    with_value,
)

log = logging.getLogger(__name__)

PREVIEW_DELAY_MS = 80    # debounce slider drags before touching the renderer
POLL_MS = 250            # bring-to-front requests and offsets label refresh

SECTIONS = (("Animação", "wave"), ("Modo berimbau", "audio"), ("Desempenho", "render"))
WAVE_ONLY = ("wave", "audio")  # sections that only affect the procedural wave

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


def _autostart_enabled() -> bool:
    try:
        from ginga import autostart

        return autostart.is_enabled()
    except (ImportError, OSError):  # winreg missing off Windows
        return False


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
        self._toggles: dict[str, tk.BooleanVar] = {}
        self._section_widgets: dict[str, list] = {}

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
        style.configure("Error.TLabel", foreground="#b3261e", font=("Segoe UI", 8))

        body = ttk.Frame(root, padding=(20, 16, 20, 8))
        body.grid(sticky="nsew")
        row = self._background_section(body, 0)
        for title, section in SECTIONS:
            ttk.Label(body, text=title, style="Section.TLabel").grid(
                row=row, column=0, columnspan=3, sticky="w", pady=(8, 4)
            )
            row += 1
            toggles = [t for t in TOGGLES if t.section == section]
            for t in (t for t in toggles if t.before_sliders):
                row = self._toggle(body, t, row, pady=(0, 6))
            for f in (f for f in FIELDS if f.section == section):
                row = self._slider(body, f, row)
            for t in (t for t in toggles if not t.before_sliders):
                row = self._toggle(body, t, row)
        self._autostart_var = tk.BooleanVar(value=_autostart_enabled())
        ttk.Checkbutton(body, text="Iniciar com o Windows", variable=self._autostart_var).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(4, 0)
        )
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

        self._refresh_background()
        self._poll_job = root.after(POLL_MS, self._poll)
        root.lift()
        root.attributes("-topmost", True)
        root.after(300, lambda: root.attributes("-topmost", False))
        root.focus_force()

    # -- widgets ------------------------------------------------------------------------

    def _background_section(self, parent, row: int) -> int:
        import tkinter as tk
        from tkinter import ttk

        ttk.Label(parent, text="Fundo", style="Section.TLabel").grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(0, 4)
        )
        row += 1
        self._kind = tk.StringVar(value=self.working.background.kind)
        choices = ttk.Frame(parent)
        choices.grid(row=row, column=0, columnspan=3, sticky="w")
        for value, text in (("wave", "Onda animada"), ("media", "Imagem, GIF ou vídeo")):
            ttk.Radiobutton(
                choices, text=text, value=value, variable=self._kind, command=self._on_kind,
            ).pack(side="left", padx=(0, 16))
        row += 1

        self._file_label = ttk.Label(parent, text="", width=44)
        self._file_label.grid(row=row, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Button(parent, text="Escolher arquivo…", command=self._ask_file).grid(
            row=row, column=2, sticky="e", pady=(6, 0)
        )
        row += 1

        ttk.Label(parent, text="Encaixe").grid(row=row, column=0, sticky="w", pady=(6, 0))
        self._fit = ttk.Combobox(
            parent, state="readonly", width=30, values=[label for _, label in FIT_LABELS],
        )
        self._fit.grid(row=row, column=1, columnspan=2, sticky="w", pady=(6, 0))
        self._fit.bind("<<ComboboxSelected>>", lambda _e: self._on_fit())
        row += 1

        self._media_hint = ttk.Label(parent, text="", style="Hint.TLabel", wraplength=460)
        self._media_hint.grid(row=row, column=0, columnspan=3, sticky="w", pady=(2, 6))
        return row + 1

    def _refresh_background(self) -> None:
        bg = self.working.background
        media = bg.kind == "media"
        self._kind.set(bg.kind)
        self._file_label.configure(text=Path(bg.path).name if bg.path else "Nenhum arquivo escolhido")
        self._fit.current([key for key, _ in FIT_LABELS].index(bg.fit))
        self._fit.state(["!disabled" if media else "disabled", "readonly"])
        problem = media_problem(bg.path) if media else None
        if problem:
            self._media_hint.configure(
                text=problem + " A onda animada continua no lugar.", style="Error.TLabel"
            )
        else:
            self._media_hint.configure(
                text="A imagem cobre todos os monitores e segue o alinhamento. "
                     "Animação e modo berimbau valem só para a onda.",
                style="Hint.TLabel",
            )
        for section in WAVE_ONLY:
            for widget in self._section_widgets.get(section, []):
                widget.state(["disabled" if media else "!disabled"])

    def _on_kind(self) -> None:
        kind = self._kind.get()
        if kind == "media" and not self.working.background.path:
            if not self._ask_file():
                self._kind.set("wave")
            return  # _ask_file already applied the choice
        self.working = with_background(self.working, kind=kind)
        self._refresh_background()
        self._schedule_preview()

    def _ask_file(self) -> bool:
        from tkinter import filedialog

        current = self.working.background.path
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Escolha a imagem, GIF ou vídeo do fundo",
            filetypes=MEDIA_FILETYPES,
            initialdir=str(Path(current).parent) if current else str(Path.home() / "Pictures"),
        )
        if not path:
            return False
        self.working = with_background(self.working, path=str(Path(path)))
        self._refresh_background()
        self._schedule_preview()
        return True

    def _on_fit(self) -> None:
        fit = FIT_LABELS[self._fit.current()][0]
        self.working = with_background(self.working, fit=fit)
        self._schedule_preview()

    def _slider(self, parent, f: Field, row: int) -> int:
        import tkinter as tk
        from tkinter import ttk

        value = get_value(self.working, f)
        var = tk.DoubleVar(value=value)
        self._values[f.key] = var
        ttk.Label(parent, text=f.label).grid(row=row, column=0, sticky="w", padx=(0, 16))
        scale = ttk.Scale(
            parent, from_=f.minimum, to=f.maximum, variable=var, length=280,
            command=lambda v, f=f: self._on_slide(f, float(v)),
        )
        scale.grid(row=row, column=1, sticky="ew")
        self._section_widgets.setdefault(f.section, []).append(scale)
        label = ttk.Label(parent, text=format_value(f, value), width=6, anchor="e")
        label.grid(row=row, column=2, sticky="e")
        self._labels[f.key] = label
        ttk.Label(parent, text=f.hint, style="Hint.TLabel").grid(
            row=row + 1, column=0, columnspan=3, sticky="w", pady=(0, 6)
        )
        return row + 2

    def _toggle(self, parent, t: Toggle, row: int, pady=(4, 0)) -> int:
        import tkinter as tk
        from tkinter import ttk

        var = tk.BooleanVar(value=get_toggle(self.working, t))
        self._toggles[t.key] = var
        check = ttk.Checkbutton(
            parent, text=t.label, variable=var, command=lambda t=t: self._on_toggle(t),
        )
        check.grid(row=row, column=0, columnspan=3, sticky="w", pady=pady)
        self._section_widgets.setdefault(t.section, []).append(check)
        return row + 1

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
        for t in TOGGLES:
            self._toggles[t.key].set(get_toggle(self.working, t))
        self._refresh_background()

    # -- events -------------------------------------------------------------------------

    def _on_slide(self, f: Field, raw: float) -> None:
        self.working = with_value(self.working, f, raw)
        self._labels[f.key].configure(text=format_value(f, get_value(self.working, f)))
        self._schedule_preview()

    def _on_toggle(self, t: Toggle) -> None:
        self.working = with_toggle(self.working, t, self._toggles[t.key].get())
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
        try:
            from ginga import autostart

            autostart.apply(bool(self._autostart_var.get()))
        except (ImportError, OSError):
            log.exception("Could not change start-with-Windows")
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
