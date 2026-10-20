"""Visual pieces: palette, the animated cat, rounded buttons, pill-shaped input, chat bubbles and a switch."""
import json, re, tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from PIL import Image, ImageTk

# Gota's identity: deep navy, a little darker and softer than before, with a violet accent
BG, BAR, SURFACE, SURFACE2, HOVER, BORDER = "#0B0E1F", "#080A17", "#0F1328", "#171C38", "#232A52", "#2B3263"
PRIMARY, PRIMARY_HOVER, ACCENT = "#6F63F2", "#8579F5", "#38BDF8"
TEXT, MUTED = "#E8EAF6", "#8F96C0"
GREEN, GREEN_HOVER, RED = "#22C58B", "#3AD9A0", "#E5484D"
KEY = "#010203"  # see-through colour of the floating cat window
FONT = ("Segoe UI", 11)
COLORS = dict(bg=BG, bar=BAR, muted=MUTED, text=TEXT, hover=HOVER)
ASSETS = Path(__file__).resolve().parent / "assets"


def _assets():
    import sys
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) / "gota" / "assets" if base else ASSETS


def lerp(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def rounded(canvas, x1, y1, x2, y2, r, **kw):
    r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)


class Sprites:
    def __init__(self):
        self.dir = _assets() / "cat"
        self.anims = json.loads((self.dir / "animations.json").read_text("utf-8"))
        self.cache = {}

    def frame(self, name, size, bg=None):
        key = (name, size, bg)
        if key not in self.cache:
            img = Image.open(self.dir / f"{name}.png").convert("RGBA").resize((size, size), Image.NEAREST)
            if bg:
                back = Image.new("RGBA", img.size, bg)
                back.alpha_composite(img)
                img = back
            self.cache[key] = ImageTk.PhotoImage(img)
        return self.cache[key]


_SPRITES = None


def sprites():
    global _SPRITES
    if _SPRITES is None:
        _SPRITES = Sprites()
    return _SPRITES


class CatView(tk.Label):
    """A label that plays one of the cat's animations (idle, listen, read, paint, talk, phone_*)."""

    def __init__(self, parent, size=96, bg=BG, **kw):
        super().__init__(parent, bg=bg, bd=0, highlightthickness=0, **kw)
        self.size, self.bgc, self.name, self.job = size, bg, None, None
        self.play("anim_cat_idle")

    def play(self, name):
        if name == self.name:
            return
        self.name = name
        if self.job:
            self.after_cancel(self.job)
        self._step(0)

    def _step(self, i):
        frames = sprites().anims[self.name]
        frame, ms = frames[i % len(frames)]
        self.configure(image=sprites().frame(frame, self.size, self.bgc))
        self.job = self.after(ms, self._step, i + 1)

    def destroy(self):
        if self.job:
            self.after_cancel(self.job)
        super().destroy()


class RoundButton(tk.Canvas):
    """A pill (or circle) button that fades smoothly between its normal and hover colours."""

    def __init__(self, parent, text, command, bg=SURFACE2, hover=HOVER, fg=TEXT, height=38, width=None, font=FONT, parent_bg=BG, circle=False):
        font_w = max(8, font[1]) * 0.95
        w = width or (height if circle else int(len(text) * font_w + 34))
        super().__init__(parent, width=w, height=height, bg=parent_bg, highlightthickness=0, bd=0, cursor="hand2")
        self.bg, self.hover, self.cmd, self.t, self.target, self.job = bg, hover, command, 0.0, 0.0, None
        self.shape = rounded(self, 1, 1, w - 1, height - 1, height / 2, fill=bg, outline="")
        self.label = self.create_text(w / 2, height / 2, text=text, fill=fg, font=font)
        self.bind("<Enter>", lambda e: self._go(1.0))
        self.bind("<Leave>", lambda e: self._go(0.0))
        self.bind("<ButtonRelease-1>", lambda e: command())

    def _go(self, target):
        self.target = target
        if self.job is None:
            self._tick()

    def _tick(self):
        self.t += (self.target - self.t) * 0.45
        if abs(self.target - self.t) < 0.03:
            self.t = self.target
        self.itemconfigure(self.shape, fill=lerp(self.bg, self.hover, self.t))
        self.job = self.after(16, self._tick) if self.t != self.target else None

    def set(self, text=None, bg=None, hover=None, fg=None):
        if text is not None:
            self.itemconfigure(self.label, text=text)
        if fg is not None:
            self.itemconfigure(self.label, fill=fg)
        if bg:
            self.bg = bg
        if hover:
            self.hover = hover
        self.itemconfigure(self.shape, fill=lerp(self.bg, self.hover, self.t))


class PillEntry(tk.Canvas):
    """A multi-line text box inside a rounded pill that grows (up to 5 lines) as you type."""

    def __init__(self, parent, on_enter, parent_bg=BG, fill=SURFACE2, hint="Fale com o Gota..."):
        super().__init__(parent, height=46, bg=parent_bg, highlightthickness=0, bd=0)
        self.fill, self.hint, self.on_enter, self.hint_on = fill, hint, on_enter, True
        self.shape = None
        self.text = tk.Text(self, height=1, bg=fill, fg=MUTED, insertbackground=TEXT, relief="flat", font=("Segoe UI", 12), wrap="word", bd=0, highlightthickness=0, padx=2, pady=0)
        self.win = self.create_window(22, 23, window=self.text, anchor="w")
        self.bind("<Configure>", lambda e: self._layout())
        self.text.bind("<Return>", lambda e: (on_enter(), "break")[1])
        self.text.bind("<Shift-Return>", lambda e: None)
        self.text.bind("<KeyRelease>", lambda e: self._grow())
        self.text.bind("<FocusIn>", lambda e: self._hint(False))
        self.text.bind("<FocusOut>", lambda e: self._hint(True))
        self._hint(True)

    def _hint(self, show):
        if show and not self.get():
            self.hint_on = True
            self.text.delete("1.0", "end")
            self.text.insert("1.0", self.hint)
            self.text.configure(fg=MUTED)
        elif not show and self.hint_on:
            self.hint_on = False
            self.text.delete("1.0", "end")
            self.text.configure(fg=TEXT)

    def _grow(self):
        lines = min(5, int(self.text.index("end-1c").split(".")[0]))
        self.text.configure(height=lines)
        self.configure(height=24 + lines * 22)
        self._layout()

    def _layout(self):
        w, h = self.winfo_width(), int(self["height"])
        if self.shape:
            self.delete(self.shape)
        self.shape = rounded(self, 1, 1, w - 1, h - 1, 23 if h < 70 else 22, fill=self.fill, outline="")
        self.tag_lower(self.shape)
        self.coords(self.win, 22, h / 2)
        self.itemconfigure(self.win, width=max(50, w - 44))

    def get(self):
        return "" if self.hint_on else self.text.get("1.0", "end").strip()

    def set(self, value):
        self.hint_on = False
        self.text.configure(fg=TEXT)
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value)
        self._grow()
        if not value:
            self._hint(self.focus_get() is not self.text)

    def clear(self):
        self.set("")
        self.text.focus_set()

    def focus(self):
        self.text.focus_set()


CODE_BG, CODE_BAR = "#080B1A", "#121733"
_FENCE = re.compile(r"```([\w+#.-]*)[ \t]*\n?(.*?)(?:```|\Z)", re.S)
_INLINE = re.compile(r"(\*\*[^*\n]+\*\*|`[^`\n]+`)")


def split_blocks(text):
    """[('text', str) | ('code', lang, code)]: fenced ``` blocks become code, everything else stays prose."""
    out, pos = [], 0
    for m in _FENCE.finditer(text):
        if m.start() > pos and text[pos:m.start()].strip():
            out.append(("text", text[pos:m.start()].strip("\n")))
        code = m.group(2).strip("\n")
        if code.strip():
            out.append(("code", m.group(1).lower(), code))
        pos = m.end()
    if pos < len(text) and text[pos:].strip():
        out.append(("text", text[pos:].strip("\n")))
    return out or [("text", text)]


def _est_lines(text, font, width):
    """How many lines `text` takes at `width` pixels (word wrap), to size a text box before it is on screen."""
    n = 0
    for line in text.split("\n"):
        cur, count = 0, 1
        for word in line.split(" "):
            w = font.measure(word + " ")
            if cur and cur + w > width:
                count, cur = count + 1, 0
            cur += w
        n += count
    return max(1, n)


def _selectable(widget, root):
    """Makes a Text read-only but selectable and copyable (Ctrl+C, Ctrl+A, right click)."""
    def keys(e):
        if e.state & 0x4 and e.keysym.lower() in ("c", "a"):
            return None
        if e.keysym in ("Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next", "Shift_L", "Shift_R", "Control_L", "Control_R"):
            return None
        return "break"
    widget.bind("<Key>", keys)
    widget.bind("<<Paste>>", lambda e: "break")
    widget.bind("<<Cut>>", lambda e: "break")
    widget.bind("<Button-1>", lambda e: widget.focus_set(), add="+")
    widget.bind("<Control-a>", lambda e: (widget.tag_add("sel", "1.0", "end-1c"), "break")[1])
    menu = tk.Menu(widget, tearoff=0, bg=SURFACE2, fg=TEXT, activebackground=PRIMARY, bd=0)

    def copy(all_text=False):
        try:
            data = widget.get("1.0", "end-1c") if all_text or not widget.tag_ranges("sel") else widget.get("sel.first", "sel.last")
        except tk.TclError:
            data = widget.get("1.0", "end-1c")
        root.clipboard_clear()
        root.clipboard_append(data)
    menu.add_command(label="Copiar", command=copy)
    menu.add_command(label="Copiar tudo", command=lambda: copy(True))
    widget.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))


def _fit_height(t):
    """After the box is on screen, sets its height to exactly the number of wrapped lines it shows."""
    try:
        crossed = t.count("1.0", "end-1c", "displaylines")   # Tk counts the line breaks BETWEEN the two indices: a 2-line paragraph gives 1
        crossed = crossed[0] if isinstance(crossed, (tuple, list)) else (crossed or 0)
        n = max(1, int(crossed) + 1)
    except (tk.TclError, TypeError, ValueError):
        return
    if int(t["height"]) != n:
        t.configure(height=n)


def _prose(parent, text, font, bg, width_px, root):
    f = tkfont.Font(font=font)
    chars = max(8, width_px // max(1, f.measure("0")))
    t = tk.Text(parent, width=chars, height=_est_lines(text, f, width_px), wrap="word", bg=bg, fg=TEXT, font=font, relief="flat", bd=0, highlightthickness=0,
                padx=0, pady=0, cursor="xterm", selectbackground=ACCENT, selectforeground="#0B0E1F", inactiveselectbackground=HOVER, insertwidth=0, takefocus=0)
    t.tag_configure("b", font=(font[0], font[1], "bold"))
    t.tag_configure("m", font=("Consolas", font[1] - 1), background=CODE_BG, foreground="#E7E9FF")
    for part in _INLINE.split(text):
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            t.insert("end", part[2:-2], "b")
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            t.insert("end", part[1:-1], "m")
        else:
            t.insert("end", part)
    _selectable(t, root)
    t.bind("<Configure>", lambda e: _fit_height(t))
    return t


def _code_block(parent, lang, code, root, width_px):
    box = tk.Frame(parent, bg=CODE_BG, highlightthickness=1, highlightbackground=HOVER, bd=0)
    bar = tk.Frame(box, bg=CODE_BAR)
    bar.pack(fill="x")
    tk.Label(bar, text=lang or "código", bg=CODE_BAR, fg=MUTED, font=("Segoe UI", 9), padx=10, pady=3).pack(side="left")
    btn = tk.Label(bar, text="⧉  Copiar", bg=CODE_BAR, fg=TEXT, font=("Segoe UI", 9), padx=10, pady=3, cursor="hand2")
    btn.pack(side="right")

    def copy():
        root.clipboard_clear()
        root.clipboard_append(code)
        btn.configure(text="✓  Copiado", fg=GREEN)
        btn.after(1600, lambda: btn.winfo_exists() and btn.configure(text="⧉  Copiar", fg=TEXT))
    btn.bind("<Button-1>", lambda e: copy())
    btn.bind("<Enter>", lambda e: btn.configure(bg=HOVER))
    btn.bind("<Leave>", lambda e: btn.configure(bg=CODE_BAR))
    mono = ("Consolas", 10)
    f = tkfont.Font(font=mono)
    inner = width_px - 20
    chars = max(10, inner // max(1, f.measure("0")))
    t = tk.Text(box, width=chars, height=_est_lines(code, f, inner), wrap="word", bg=CODE_BG, fg="#E7E9FF", font=mono, relief="flat", bd=0, highlightthickness=0,
                padx=10, pady=8, cursor="xterm", selectbackground=ACCENT, selectforeground="#0B0E1F", inactiveselectbackground=HOVER, insertwidth=0, takefocus=0)
    t.insert("1.0", code)
    _selectable(t, root)
    t.bind("<Configure>", lambda e: _fit_height(t))
    t.pack(fill="x")
    return box


class ChatInput(tk.Canvas):
    """The message box: a rounded card with the text on top and the buttons (attach, mic, send) along its bottom edge."""

    def __init__(self, parent, on_enter, left=(), right=(), parent_bg=BG, hint="Escreva para o Gota…"):
        super().__init__(parent, height=96, bg=parent_bg, highlightthickness=0, bd=0)
        self.fill, self.hint, self.on_enter, self.hint_on = SURFACE2, hint, on_enter, True
        self.shape = None
        self.text = tk.Text(self, height=1, bg=self.fill, fg=MUTED, insertbackground=TEXT, relief="flat", font=("Segoe UI", 12), wrap="word", bd=0, highlightthickness=0, padx=2, pady=0)
        self.win = self.create_window(20, 16, window=self.text, anchor="nw")
        self.buttons, self.left_names, self.right_names = {}, [], []
        for name, glyph, cmd in left:
            self.buttons[name] = RoundButton(self, glyph, cmd, bg=self.fill, hover=HOVER, circle=True, height=34, font=("Segoe UI", 13), parent_bg=self.fill)
            self.left_names.append(name)
        for name, glyph, cmd, *accent in right:
            hot = bool(accent and accent[0])
            self.buttons[name] = RoundButton(self, glyph, cmd, bg=PRIMARY if hot else self.fill, hover=PRIMARY_HOVER if hot else HOVER, circle=True, height=34, font=("Segoe UI", 13), parent_bg=self.fill)
            self.right_names.append(name)
        self.btn_win = {n: self.create_window(0, 0, window=b, anchor="center") for n, b in self.buttons.items()}
        self.bind("<Configure>", lambda e: self._layout())
        self.text.bind("<Return>", lambda e: (on_enter(), "break")[1])
        self.text.bind("<Shift-Return>", lambda e: None)
        self.text.bind("<KeyRelease>", lambda e: self._grow())
        self.text.bind("<FocusIn>", lambda e: self._hint(False))
        self.text.bind("<FocusOut>", lambda e: self._hint(True))
        self._hint(True)

    def _hint(self, show):
        if show and not self.get():
            self.hint_on = True
            self.text.delete("1.0", "end")
            self.text.insert("1.0", self.hint)
            self.text.configure(fg=MUTED)
        elif not show and self.hint_on:
            self.hint_on = False
            self.text.delete("1.0", "end")
            self.text.configure(fg=TEXT)

    def _grow(self):
        self.text.configure(height=min(6, int(self.text.index("end-1c").split(".")[0])))
        self._layout()

    def _layout(self):
        w = self.winfo_width()
        lines = int(self.text["height"])
        h = 16 + lines * 22 + 14 + 40
        self.configure(height=h)
        if self.shape:
            self.delete(self.shape)
        self.shape = rounded(self, 1, 1, w - 1, h - 1, 22, fill=self.fill, outline=BORDER)
        self.tag_lower(self.shape)
        self.coords(self.win, 20, 16)
        self.itemconfigure(self.win, width=max(50, w - 40))
        x = 26
        for n in self.left_names:
            self.coords(self.btn_win[n], x, h - 26)
            x += 40
        x = w - 26
        for n in reversed(self.right_names):
            self.coords(self.btn_win[n], x, h - 26)
            x -= 40

    def get(self):
        return "" if self.hint_on else self.text.get("1.0", "end").strip()

    def set(self, value):
        self.hint_on = False
        self.text.configure(fg=TEXT)
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value)
        self._grow()
        if not value:
            self._hint(self.focus_get() is not self.text)

    def clear(self):
        self.set("")
        self.text.focus_set()

    def focus(self):
        self.text.focus_set()


def bubble(parent, text, mine, maxw=560):
    """A chat bubble: rounded, sized to its content; the text is selectable and ``` blocks become separate code boxes with a Copy button."""
    plain = not mine
    pad_x, pad_y, r = (2, 4, 0) if plain else (16, 11, 18)
    bg = BG if plain else SURFACE2
    root = parent.winfo_toplevel()
    c = tk.Canvas(parent, bg=BG, highlightthickness=0, bd=0)
    frame = tk.Frame(c, bg=bg)
    blocks = split_blocks(text)
    inner = maxw - 2 * pad_x
    f = tkfont.Font(font=FONT)
    if any(b[0] == "code" for b in blocks):
        width = inner
    else:   # a short message gets a snug bubble
        width = min(inner, max(f.measure(line) for line in text.split("\n")) + 8)
    for i, b in enumerate(blocks):
        if b[0] == "text":
            w = _prose(frame, b[1], FONT, bg, width, root)
        else:
            w = _code_block(frame, b[1], b[2], root, width)
        w.pack(fill="x", pady=(0 if i == 0 else 8, 0))
    win = c.create_window(pad_x, pad_y, window=frame, anchor="nw")
    state = {"shape": None}

    def layout(_=None):
        frame.update_idletasks()
        w, h = frame.winfo_reqwidth() + 2 * pad_x, frame.winfo_reqheight() + 2 * pad_y
        c.configure(width=w, height=h)
        if state["shape"]:
            c.delete(state["shape"])
        if not plain:
            state["shape"] = rounded(c, 0, 0, w, h, r, fill=bg, outline="")
            c.tag_lower(state["shape"])
    frame.bind("<Configure>", layout)
    layout()
    return c


class Toggle(tk.Canvas):
    """An on/off switch that slides."""

    def __init__(self, parent, value, command, parent_bg=SURFACE):
        super().__init__(parent, width=42, height=24, bg=parent_bg, highlightthickness=0, bd=0, cursor="hand2")
        self.value, self.command, self.pos = bool(value), command, 1.0 if value else 0.0
        self.bind("<Button-1>", lambda e: self.flip())
        self._draw()

    def flip(self):
        self.value = not self.value
        self._anim()
        self.command(self.value)

    def _anim(self):
        goal = 1.0 if self.value else 0.0
        self.pos += (goal - self.pos) * 0.5
        if abs(goal - self.pos) < 0.04:
            self.pos = goal
        self._draw()
        if self.pos != goal:
            self.after(16, self._anim)

    def _draw(self):
        self.delete("all")
        rounded(self, 1, 2, 41, 22, 10, fill=lerp(HOVER, GREEN, self.pos), outline="")
        x = 12 + 18 * self.pos
        self.create_oval(x - 8, 4, x + 8, 20, fill=TEXT, outline="")
