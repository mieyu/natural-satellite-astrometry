"""Scrollable, zoomable viewer for a generated PNG result."""

import tkinter as tk
from pathlib import Path
from tkinter import ttk


class ResultImageViewer(tk.Toplevel):
    ZOOM_LEVELS = (0.125, 0.25, 0.5, 1, 2)

    def __init__(self, master, path: Path):
        super().__init__(master)
        self.title(f"查看结果图 - {path.name}")
        self.geometry(
            f"{min(1100, self.winfo_screenwidth() - 80)}x"
            f"{min(750, self.winfo_screenheight() - 100)}"
        )
        self._source = tk.PhotoImage(file=str(path))
        self._display = None
        self._zoom_index = self.ZOOM_LEVELS.index(1)
        self._initial_fit_pending = True

        toolbar = ttk.Frame(self, padding=6)
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="−", width=3, command=lambda: self._step(-1)).pack(side="left")
        ttk.Button(toolbar, text="+", width=3, command=lambda: self._step(1)).pack(side="left", padx=(4, 10))
        ttk.Button(toolbar, text="适合窗口", command=self.fit_window).pack(side="left")
        ttk.Button(toolbar, text="原始尺寸", command=lambda: self._set_zoom(1)).pack(side="left", padx=6)
        self.zoom_text = ttk.Label(toolbar)
        self.zoom_text.pack(side="left", padx=8)
        ttk.Label(toolbar, text="滚轮缩放 · 按住左键拖动").pack(side="right")

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(body, background="#f5f5f5", highlightthickness=0, cursor="fleur")
        vbar = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        hbar = ttk.Scrollbar(body, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns")
        hbar.grid(row=1, column=0, sticky="ew")
        self._image_item = self.canvas.create_image(0, 0, anchor="nw")
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Button-4>", lambda _event: self._step(1))
        self.canvas.bind("<Button-5>", lambda _event: self._step(-1))
        self.canvas.bind("<ButtonPress-1>", self._pan_start)
        self.canvas.bind("<B1-Motion>", self._pan_drag)
        self.canvas.bind("<Configure>", self._initial_fit)
        self.bind("<Escape>", lambda _event: self.destroy())

    def _initial_fit(self, event):
        if self._initial_fit_pending and event.width > 100 and event.height > 100:
            self._initial_fit_pending = False
            self.after_idle(self.fit_window)

    def _set_zoom(self, level):
        old = self._display
        center_x = self.canvas.canvasx(self.canvas.winfo_width() / 2)
        center_y = self.canvas.canvasy(self.canvas.winfo_height() / 2)
        self._zoom_index = self.ZOOM_LEVELS.index(level)
        if level < 1:
            self._display = self._source.subsample(int(1 / level))
        elif level > 1:
            self._display = self._source.zoom(int(level))
        else:
            self._display = self._source
        self.canvas.itemconfigure(self._image_item, image=self._display)
        width, height = self._display.width(), self._display.height()
        self.canvas.configure(scrollregion=(0, 0, width, height))
        self.zoom_text.configure(text=f"{level * 100:g}%")
        if old is not None:
            center_x *= width / old.width()
            center_y *= height / old.height()
            self.canvas.xview_moveto(max(0, (center_x - self.canvas.winfo_width() / 2) / width))
            self.canvas.yview_moveto(max(0, (center_y - self.canvas.winfo_height() / 2) / height))

    def _step(self, change):
        index = min(max(self._zoom_index + change, 0), len(self.ZOOM_LEVELS) - 1)
        self._set_zoom(self.ZOOM_LEVELS[index])

    def fit_window(self):
        width = max(self.canvas.winfo_width() - 8, 1)
        height = max(self.canvas.winfo_height() - 8, 1)
        level = next((value for value in reversed(self.ZOOM_LEVELS)
                      if self._source.width() * value <= width
                      and self._source.height() * value <= height), self.ZOOM_LEVELS[0])
        self._set_zoom(level)
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)

    def _wheel(self, event):
        self._step(1 if event.delta > 0 else -1)
        return "break"

    def _pan_start(self, event):
        self.canvas.scan_mark(event.x, event.y)

    def _pan_drag(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)
