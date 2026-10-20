"""Small reusable pieces: the colours of the app, the animated cat and the round-ish chat bubbles."""
import json, tkinter as tk
from pathlib import Path
from PIL import Image, ImageTk

BG, SURFACE, SURFACE2 = "#0F1222", "#1A1F3A", "#262B4A"
PRIMARY, ACCENT, TEXT, MUTED = "#7C5CFC", "#22D3EE", "#FFFFFF", "#A0A4C1"
GREEN, RED = "#22C55E", "#EF4444"
KEY = "#010203"  # becomes see-through in the floating cat window
FONT = ("Segoe UI", 11)
ASSETS = Path(__file__).resolve().parent / "assets"


def _frozen_assets():
    import sys
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) / "gota" / "assets" if base else ASSETS


class Sprites:
    """Loads the cat's frames once per size and knows each animation (frame, milliseconds)."""

    def __init__(self):
        self.dir = _frozen_assets() / "cat"
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


SPRITES = None


def sprites():
    global SPRITES
    if SPRITES is None:
        SPRITES = Sprites()
    return SPRITES


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


def bubble(parent, text, mine, width=520):
    """A chat bubble: a coloured frame with wrapped text (selectable via right-click copy)."""
    holder = tk.Frame(parent, bg=BG)
    box = tk.Frame(holder, bg=PRIMARY if mine else SURFACE2, padx=14, pady=9)
    label = tk.Label(box, text=text, bg=box["bg"], fg=TEXT, font=FONT, justify="left", wraplength=width, anchor="w")
    label.pack()
    box.pack(side="right" if mine else "left")
    menu = tk.Menu(label, tearoff=0)
    menu.add_command(label="Copiar", command=lambda: (parent.clipboard_clear(), parent.clipboard_append(text)))
    label.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))
    return holder, label


def button(parent, text, command, bg=PRIMARY, fg=TEXT, width=None, font=FONT):
    b = tk.Button(parent, text=text, command=command, bg=bg, fg=fg, activebackground=ACCENT, activeforeground=BG,
                  relief="flat", bd=0, padx=16, pady=8, font=font, cursor="hand2", width=width)
    return b
