"""The cat that slides up from the bottom of the screen, over any program, listens, answers and slides down."""
import tkinter as tk
from .widgets import BG, KEY, MUTED, SURFACE2, TEXT, FONT, CatView


class CatOverlay:
    SIZE = 150

    def __init__(self, root):
        self.root = root
        self.win = None
        self.hide_job = None

    def _build(self):
        w = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg=KEY)
        w.attributes("-transparentcolor", KEY)
        self.bubble = tk.Label(w, text="", bg=SURFACE2, fg=TEXT, font=FONT, wraplength=340, justify="left", padx=14, pady=10)
        self.cat = CatView(w, size=self.SIZE, bg=KEY)
        self.bubble.pack(side="top", anchor="e", padx=(0, 20), pady=(0, 4))
        self.cat.pack(side="top", anchor="e")
        self.cat.bind("<Button-1>", lambda e: self.hide())
        self.bubble.bind("<Button-1>", lambda e: self.hide())
        self.win = w

    def show(self, text, mood="anim_cat_idle"):
        if self.hide_job:
            self.root.after_cancel(self.hide_job)
            self.hide_job = None
        fresh = self.win is None or not self.win.winfo_exists()
        if fresh:
            self._build()
        self.set(text, mood)
        if fresh:
            self.win.update_idletasks()
            sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
            self.w, self.h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
            self.x, self.y_end = sw - self.w - 24, sh - self.h - 56
            self._slide(sh, self.y_end)

    def set(self, text, mood=None):
        if self.win is None or not self.win.winfo_exists():
            return
        self.bubble.configure(text=text)
        if mood:
            self.cat.play(mood)
        self.win.update_idletasks()
        self.w, self.h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        sh = self.win.winfo_screenheight()
        self.y_end = sh - self.h - 56
        y = self.win.winfo_y() if self.win.winfo_y() > 0 else sh
        self.win.geometry(f"{self.w}x{self.h}+{self.win.winfo_screenwidth() - self.w - 24}+{min(max(y, self.y_end), sh)}")

    def _slide(self, y, target, step=0):
        if self.win is None or not self.win.winfo_exists():
            return
        # ease-out towards the target
        y = target + int((y - target) * 0.72)
        self.win.geometry(f"{self.w}x{self.h}+{self.x}+{y}")
        if abs(y - target) > 1:
            self.win.after(16, self._slide, y, target)
        else:
            self.win.geometry(f"{self.w}x{self.h}+{self.x}+{target}")

    def hide_later(self, ms=700):
        if self.hide_job:
            self.root.after_cancel(self.hide_job)
        self.hide_job = self.root.after(ms, self.hide)

    def hide(self):
        if self.win is None or not self.win.winfo_exists():
            return
        sh = self.win.winfo_screenheight()
        win = self.win

        def down(y):
            if not win.winfo_exists():
                return
            if y >= sh:
                win.destroy()
                self.win = None
                return
            win.geometry(f"{self.w}x{self.h}+{self.x}+{y}")
            win.after(16, down, y + 24)
        down(win.winfo_y())

    @property
    def visible(self):
        return self.win is not None and self.win.winfo_exists()
