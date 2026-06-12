from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional


# =========================
# Theme (Light Mode)
# =========================
BG_TOP = "#F8FAFC"       # Светлый верхний градиент (Slate 50)
BG_BOTTOM = "#E2E8F0"    # Светлый нижний градиент (Slate 200)
APP_BG = "#F1F5F9"       # Фоновый цвет контейнера
CARD_BG = "#FFFFFF"      # Чисто белая карточка
CARD_BORDER = "#CBD5E1"  # Мягкая серая граница для карточки
TEXT = "#0F172A"         # Темно-синий/черный текст для отличной читаемости (Slate 900)
MUTED = "#64748B"        # Приглушенный серый текст (Slate 500)
ACCENT = "#0066CC"       # macOS Light Blue (Яркий синий)
ACCENT_DARK = "#0052A3"  # Темно-синий для эффекта наведения (hover primary)
BTN_BG = "#E2E8F0"       # Светло-серый фон для обычной кнопки
BTN_BG_HOVER = "#CBD5E1" # Серый чуть темнее при наведении на обычную кнопку

SW_ON = "#34C759"        # Яркий зеленый Apple для Toggle ON
SW_OFF = "#E9E9EB"       # Светло-серый Apple для Toggle OFF
SW_KNOB = "#FFFFFF"      # Белый бегунок переключателя


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

        steps = min(220, h)
        for i in range(steps):
            t = i / max(1, steps - 1)
            col = _blend(self.c1, self.c2, t)
            y1 = int(i * h / steps)
            y2 = int((i + 1) * h / steps)
            self.create_rectangle(0, y1, w, y2, fill=col, outline=col, tags="grad")


class Card(tk.Canvas):
    """Rounded card with soft shadow adapted for light mode."""
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

        # Мягкая полупрозрачная тень для светлого режима
        shadow_off = 4
        _rounded_rect(
            self,
            8 + shadow_off, 8 + shadow_off,
            w - 8 + shadow_off, h - 8 + shadow_off,
            r=self.radius,
            fill="#CBD5E1",  # Светлая серая тень вместо черной
            outline="",
            tags="card"
        )

        # Основное тело карточки
        _rounded_rect(
            self,
            8, 8, w - 8, h - 8,
            r=self.radius,
            fill=CARD_BG,
            outline=CARD_BORDER,
            width=1,
            tags="card"
        )

        inner_w = max(10, w - 2 * (8 + self.pad))
        inner_h = max(10, h - 2 * (8 + self.pad))
        self.coords(self._win_id, 8 + self.pad, 8 + self.pad)
        self.itemconfigure(self._win_id, width=inner_w, height=inner_h)


class SoftButton(tk.Canvas):
    """Canvas-based rounded button supporting modern themes and animations."""
    def __init__(self, master, text: str, command: Callable[[], None], kind: str = "secondary", width: int = 140, height: int = 38, radius: int = 12):
        super().__init__(master, width=width, height=height, highlightthickness=0, bd=0, bg=master["bg"])
        self.command = command
        self.width = width
        self.height = height
        self.radius = radius
        self.text = text

        if kind == "primary":
            self.bg_color = ACCENT
            self.hover_color = ACCENT_DARK
            self.fg_color = "white"
        else:
            self.bg_color = BTN_BG
            self.hover_color = BTN_BG_HOVER
            self.fg_color = TEXT

        self.current_bg = self.bg_color

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        
        self.configure(cursor="hand2")
        self.redraw()

    def redraw(self):
        self.delete("all")
        
        _rounded_rect(
            self, 
            0, 0, self.width, self.height, 
            r=self.radius, 
            fill=self.current_bg, 
            outline=""
        )
        
        self.create_text(
            self.width // 2, self.height // 2,
            text=self.text,
            fill=self.fg_color,
            font=("Segoe UI", 10, "bold"),
            justify="center"
        )

    def _on_enter(self, _evt=None):
        self.current_bg = self.hover_color
        self.redraw()

    def _on_leave(self, _evt=None):
        self.current_bg = self.bg_color
        self.redraw()

    def _on_click(self, _evt=None):
        if self.command:
            self.command()

    def configure(self, **kwargs):
        if "text" in kwargs:
            self.text = kwargs.pop("text")
            self.redraw()
        super().configure(**kwargs)

    config = configure


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

        # Отрегулирована граница для выключенного состояния, чтобы переключатель не терялся на белом фоне
        outline_color = track if on else CARD_BORDER
        _rounded_rect(self, 1, 1, self.w - 1, self.h - 1, r=self.r, fill=track, outline=outline_color)

        margin = 3
        knob_d = self.h - 2 * margin
        x1 = (self.w - margin - knob_d) if on else margin
        y1 = margin
        # Тень под бегунком переключателя
        self.create_oval(x1, y1, x1 + knob_d, y1 + knob_d, fill=SW_KNOB, outline="#CBD5E1")


class ModernSlider(tk.Canvas):
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
        self._track_h = 8
        self._knob_r = 9

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

        x0 = self._pad
        x1 = self.w - self._pad
        cy = self.h // 2
        th = self._track_h
        r = th // 2

        # Светлая дорожка слайдера
        _rounded_rect(self, x0, cy - th/2, x1, cy + th/2, r=r, fill="#E2E8F0", outline="#E2E8F0")

        try:
            v = float(self.var.get())
        except (ValueError, tk.TclError):
            v = self.from_
        v = self._clamp(v)
        vx = self._x_from_value(v)

        # Заполненная дорожка слайдера акцентным синим цветом
        _rounded_rect(self, x0, cy - th/2, vx, cy + th/2, r=r, fill=ACCENT, outline=ACCENT)

        kr = self._knob_r
        # Тень и сам круглый бегунок
        self.create_oval(vx-kr-1, cy-kr+1, vx+kr-1, cy+kr+1, fill="#CBD5E1", outline="")
        self.create_oval(vx-kr, cy-kr, vx+kr, cy+kr, fill="#FFFFFF", outline="#94A3B8")


def soft_text(parent: tk.Misc, height=10, readonly: bool = False) -> tk.Text:
    t = tk.Text(
        parent,
        wrap="word",
        height=height,
        font=("Consolas", 10),
        bg="#F8FAFC",            # Светлое текстовое поле
        fg=TEXT,
        insertbackground=TEXT,
        bd=0,
        highlightthickness=1,
        highlightbackground=CARD_BORDER,
        highlightcolor=ACCENT,
        padx=10,
        pady=8
    )
    if readonly:
        t.configure(state="disabled")
    return t


# =========================
# Демонстрационное окно
# =========================
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Modern UI Light Mode")
    root.geometry("500x450")
    
    # Создаем градиентный фон приложения
    bg_gradient = GradientBackground(root, BG_TOP, BG_BOTTOM)
    bg_gradient.pack(fill="both", expand=True)

    # Создаем белую карточку по центру
    card = Card(bg_gradient, radius=20, pad=16)
    card.place(relx=0.5, rely=0.5, width=360, height=340, anchor="center")

    # Контент внутри карточки
    body = card.body

    # Заголовок
    lbl = tk.Label(body, text="Light Theme Active", font=("Segoe UI", 14, "bold"), bg=CARD_BG, fg=TEXT)
    lbl.pack(pady=(10, 5))
    
    lbl_sub = tk.Label(body, text="Clean & crisp user interface", font=("Segoe UI", 10), bg=CARD_BG, fg=MUTED)
    lbl_sub.pack(pady=(0, 15))

    # Кнопки
    btn_prim = SoftButton(body, text="Primary Action", command=lambda: print("Primary Clicked"), kind="primary", width=160, height=38, radius=12)
    btn_prim.pack(pady=8)

    btn_sec = SoftButton(body, text="Secondary", command=lambda: print("Secondary Clicked"), kind="secondary", width=160, height=38, radius=12)
    btn_sec.pack(pady=8)

    # Переключатель
    sw_var = tk.BooleanVar(value=True)
    switch = ToggleSwitch(body, variable=sw_var)
    switch.pack(pady=10)

    # Слайдер
    sld_var = tk.DoubleVar(value=0.5)
    slider = ModernSlider(body, variable=sld_var, from_=0.0, to=1.0)
    slider.pack(pady=10)

    root.mainloop()