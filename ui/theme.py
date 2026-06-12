from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional


# =========================
# Theme
# =========================
BG_TOP = "#DDE9FF"       # background gradient top
BG_BOTTOM = "#F2DDFF"    # background gradient bottom
APP_BG = "#EEF3FB"       # container bg (mid)
CARD_BG = "#F8FAFF"      # card bg
CARD_BORDER = "#D7DFEE"  # subtle border
TEXT = "#1C2333"
MUTED = "#6B7487"
ACCENT = "#6C63FF"       # purple/indigo
ACCENT_DARK = "#5A52F0"
BTN_BG = "#FFFFFF"
BTN_BG_HOVER = "#F1F4FA"

SW_ON = "#0A66FF"
SW_OFF = "#CBD5E1"
SW_KNOB = "#FFFFFF"


# =========================
# Helpers
# =========================
def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02X}{g:02X}{b:02X}"


def _blend(c1: str, c2: str, t: float) -> str:
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    r = int(r1 * (1 - t) + r2 * t)
    g = int(g1 * (1 - t) + g2 * t)
    b = int(b1 * (1 - t) + b2 * t)
    return _rgb_to_hex(r, g, b)


def _rounded_rect(canvas: tk.Canvas, x1, y1, x2, y2, r=16, **kwargs):
    # Smooth polygon trick for rounded rect
    points = [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1
    ]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


class GradientBackground(tk.Canvas):
    """Simple vertical gradient background."""
    def __init__(self, master: tk.Misc, c1: str, c2: str):
        super().__init__(master, highlightthickness=0, bd=0)
        self.c1 = c1
        self.c2 = c2
        self._after_id: Optional[str] = None
        self.bind("<Configure>", self._schedule_redraw)

    def _schedule_redraw(self, _evt=None):
        if self._after_id:
            self.after_cancel(self._after_id)
        self._after_id = self.after(30, self._redraw)

    def _redraw(self):
        self._after_id = None
        self.delete("grad")

        w = max(1, self.winfo_width())
        h = max(1, self.winfo_height())

        # Draw stripes (fast enough for UI)
        steps = min(220, h)  # fewer steps -> faster
        for i in range(steps):
            t = i / max(1, steps - 1)
            col = _blend(self.c1, self.c2, t)
            y1 = int(i * h / steps)
            y2 = int((i + 1) * h / steps)
            self.create_rectangle(0, y1, w, y2, fill=col, outline=col, tags="grad")


class Card(tk.Canvas):
    """Rounded card with pseudo shadow. Put widgets into card.body frame."""
    def __init__(self, master: tk.Misc, radius=18, pad=14):
        super().__init__(master, highlightthickness=0, bd=0, bg=APP_BG)
        self.radius = radius
        self.pad = pad

        self.body = tk.Frame(self, bg=CARD_BG)

        self._win_id = self.create_window(
            self.pad, self.pad,
            anchor="nw",
            window=self.body
        )
        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, _evt=None):
        w = max(1, self.winfo_width())
        h = max(1, self.winfo_height())
        self.delete("card")

        # pseudo shadow
        shadow_off = 6
        _rounded_rect(
            self,
            8 + shadow_off, 8 + shadow_off,
            w - 8 + shadow_off, h - 8 + shadow_off,
            r=self.radius,
            fill="#C9D3E6",
            outline="",
            tags="card"
        )

        # main card
        _rounded_rect(
            self,
            8, 8, w - 8, h - 8,
            r=self.radius,
            fill=CARD_BG,
            outline=CARD_BORDER,
            width=1,
            tags="card"
        )

        # inner body resize
        inner_w = max(10, w - 2 * (8 + self.pad))
        inner_h = max(10, h - 2 * (8 + self.pad))
        self.coords(self._win_id, 8 + self.pad, 8 + self.pad)
        self.itemconfigure(self._win_id, width=inner_w, height=inner_h)


class SoftButton(tk.Button):
    def __init__(self, master, text, command, kind="secondary", width=None):
        font = ("Segoe UI", 10, "bold")
        if kind == "primary":
            super().__init__(
                master, text=text, command=command,
                bg=ACCENT, fg="white",
                activebackground=ACCENT_DARK,
                activeforeground="white",
                bd=0, relief="flat",
                font=font, padx=14, pady=10,
                cursor="hand2"
            )
        else:
            super().__init__(
                master, text=text, command=command,
                bg=BTN_BG, fg=TEXT,
                activebackground=BTN_BG_HOVER,
                activeforeground=TEXT,
                bd=0, relief="flat",
                font=font, padx=14, pady=10,
                cursor="hand2"
            )
        if width is not None:
            self.configure(width=width)


class ToggleSwitch(tk.Canvas):
    def __init__(self, master, variable: tk.BooleanVar, width=50, height=24):
        super().__init__(master, width=width, height=height, highlightthickness=0, bd=0, bg=CARD_BG)
        self.var = variable
        self.w = width
        self.h = height
        self.r = height // 2
        self.bind("<Button-1>", self._toggle)
        self.var.trace_add("write", lambda *_: self.redraw())
        self.redraw()

    def _toggle(self, _evt=None):
        self.var.set(not bool(self.var.get()))

    def redraw(self):
        self.delete("all")
        on = bool(self.var.get())
        track = SW_ON if on else SW_OFF

        # track
        _rounded_rect(self, 1, 1, self.w - 1, self.h - 1, r=self.r, fill=track, outline=track)

        # knob
        margin = 3
        knob_d = self.h - 2 * margin
        x1 = (self.w - margin - knob_d) if on else margin
        y1 = margin
        self.create_oval(x1, y1, x1 + knob_d, y1 + knob_d, fill=SW_KNOB, outline="#E6EAF2")


class ModernSlider(tk.Canvas):
    """
    Canvas-based slider: looks more modern than tk.Scale.

    - value range: [from_, to]
    - variable: tk.DoubleVar
    - resolution: step (e.g. 0.05)
    """
    def __init__(
        self,
        master: tk.Misc,
        variable: tk.DoubleVar,
        from_: float,
        to: float,
        resolution: float = 0.05,
        width: int = 220,
        height: int = 26,
        command: Optional[Callable[[float], None]] = None,
    ):
        super().__init__(master, width=width, height=height, highlightthickness=0, bd=0, bg=CARD_BG)
        self.var = variable
        self.from_ = float(from_)
        self.to = float(to)
        self.resolution = float(resolution)
        self.w = width
        self.h = height
        self.command = command

        self._pad = 10
        self._track_h = 10
        self._knob_r = 10

        self.bind("<Button-1>", self._on_click)
        self.bind("<B1-Motion>", self._on_drag)

        self.var.trace_add("write", lambda *_: self.redraw())
        self.redraw()

    def _clamp(self, v: float) -> float:
        v = max(self.from_, min(self.to, v))
        if self.resolution > 0:
            steps = round((v - self.from_) / self.resolution)
            v = self.from_ + steps * self.resolution
        v = max(self.from_, min(self.to, v))
        return float(v)

    def _value_from_x(self, x: float) -> float:
        x0 = self._pad
        x1 = self.w - self._pad
        if x1 <= x0:
            return self.from_
        t = (x - x0) / (x1 - x0)
        v = self.from_ + t * (self.to - self.from_)
        return self._clamp(v)

    def _x_from_value(self, v: float) -> float:
        x0 = self._pad
        x1 = self.w - self._pad
        if self.to == self.from_:
            return x0
        t = (v - self.from_) / (self.to - self.from_)
        return x0 + t * (x1 - x0)

    def _set_value(self, v: float) -> None:
        v2 = self._clamp(v)
        try:
            self.var.set(v2)
        except tk.TclError:
            return
        if self.command:
            self.command(v2)

    def _on_click(self, event: tk.Event) -> None:
        self._set_value(self._value_from_x(float(event.x)))

    def _on_drag(self, event: tk.Event) -> None:
        self._set_value(self._value_from_x(float(event.x)))

    def redraw(self) -> None:
        self.delete("all")

        # track
        x0 = self._pad
        x1 = self.w - self._pad
        cy = self.h // 2
        th = self._track_h
        r = th // 2

        _rounded_rect(self, x0, cy - th/2, x1, cy + th/2, r=r, fill="#E7ECF6", outline="#E7ECF6")

        # filled track
        try:
            v = float(self.var.get())
        except (ValueError, tk.TclError):
            v = self.from_
        v = self._clamp(v)
        vx = self._x_from_value(v)

        _rounded_rect(self, x0, cy - th/2, vx, cy + th/2, r=r, fill=ACCENT, outline=ACCENT)

        # knob (slightly shadowed)
        kr = self._knob_r
        self.create_oval(vx-kr-1, cy-kr+1, vx+kr-1, cy+kr+1, fill="#C9D3E6", outline="")  # shadow
        self.create_oval(vx-kr, cy-kr, vx+kr, cy+kr, fill="#FFFFFF", outline="#D6DEEE")


def soft_text(parent: tk.Misc, height=10, readonly: bool = False) -> tk.Text:
    t = tk.Text(
        parent,
        wrap="word",
        height=height,
        font=("Consolas", 10),
        bg="#FFFFFF",
        fg=TEXT,
        insertbackground=TEXT,
        bd=0,
        highlightthickness=1,
        highlightbackground="#D6DEEE",
        highlightcolor=ACCENT,
        padx=10,
        pady=8
    )
    if readonly:
        t.configure(state="disabled")
    return t
