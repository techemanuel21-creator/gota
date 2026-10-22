"""The cat that slides up from the bottom of the screen, over any program, listens, answers and slides down.
Its words appear in a speech bubble that stays glued above the cat and grows upwards, never off the screen."""
import tkinter as tk
from .chrome import work_area
from .widgets import KEY, MUTED, SURFACE2, TEXT, FONT, HOVER, CatView, RoundButton, rounded, PRIMARY


class CatOverlay:
    SIZE = 150
    MAXW = 360          # bubble text width
    PAD_X, PAD_Y, TAIL = 16, 12, 12

    def __init__(self, root, maxw=360, font=FONT, size=150, buttons=None, click_hides=True):
        """buttons: [(name, glyph, command)] shown as tiny round buttons beside the cat (used by the call)."""
        self.root = root
        self.MAXW, self.font, self.SIZE = maxw, font, size
        self.button_defs, self.click_hides = buttons or [], click_hides
        self.buttons = {}
        self.win = None
        self.hide_job = None
        self.sliding = False
        self.text = ""

    def _build(self):
        w = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg=KEY)
        w.attributes("-transparentcolor", KEY)
        self.bubble = tk.Canvas(w, bg=KEY, highlightthickness=0, bd=0, cursor="hand2")
        self.bubble.pack(side="top", anchor="e", padx=(0, 12), pady=(0, 0))
        row = tk.Frame(w, bg=KEY)
        row.pack(side="top", anchor="e")
        if self.button_defs:
            col = tk.Frame(row, bg=KEY)
            col.pack(side="left", anchor="s", padx=(0, 4), pady=(0, 14))
            for name, glyph, command in self.button_defs:
                b = RoundButton(col, glyph, command, bg=SURFACE2, hover=HOVER, height=30, circle=True, font=("Segoe UI Emoji", 10), parent_bg=KEY)
                b.pack(side="left", padx=3)
                self.buttons[name] = b
        self.cat = CatView(row, size=self.SIZE, bg=KEY)
        self.cat.pack(side="left")
        if self.click_hides:
            self.cat.bind("<Button-1>", lambda e: self.hide())
            self.bubble.bind("<Button-1>", lambda e: self.hide())
        self.win = w

    # ------------------------------------------------------------------ bubble
    def _fit(self, text, max_h):
        """Draws the text in the bubble; if it would be taller than the screen allows, keeps the most recent part."""
        c = self.bubble
        c.delete("all")
        item = c.create_text(self.PAD_X, self.PAD_Y, text=text, fill=TEXT, font=self.font, width=self.MAXW, anchor="nw")
        x1, y1, x2, y2 = c.bbox(item)
        if (y2 - y1) + 2 * self.PAD_Y + self.TAIL > max_h:
            words = text.split(" ")
            while len(words) > 3 and (y2 - y1) + 2 * self.PAD_Y + self.TAIL > max_h:
                words = words[max(1, len(words) // 12):]
                c.itemconfigure(item, text="… " + " ".join(words))
                x1, y1, x2, y2 = c.bbox(item)
        w, h = (x2 - x1) + 2 * self.PAD_X, (y2 - y1) + 2 * self.PAD_Y
        c.configure(width=w + 2, height=h + self.TAIL + 1)
        shape = rounded(c, 1, 1, w, h, 20, fill=SURFACE2, outline=PRIMARY, width=1)
        tail_x = w - 46
        tail = c.create_polygon(tail_x, h - 1, tail_x + 22, h - 1, tail_x + 14, h + self.TAIL, fill=SURFACE2, outline="")
        c.create_line(tail_x + 1, h, tail_x + 14, h + self.TAIL, tail_x + 22, h, fill=PRIMARY)
        c.create_line(tail_x + 2, h - 1, tail_x + 21, h - 1, fill=SURFACE2)
        c.tag_lower(tail)
        c.tag_lower(shape)

    def _geometry(self):
        """Window size from its content, glued to the bottom-right of the work area, always inside the screen."""
        self.win.update_idletasks()
        ax, ay, aw, ah = work_area()
        self.w, self.h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        self.x = ax + aw - self.w - 20
        self.y_end = max(ay + 4, ay + ah - self.h - 8)
        self.screen_bottom = self.win.winfo_screenheight()

    # ------------------------------------------------------------------ show / update
    def show(self, text, mood="anim_cat_idle"):
        if self.hide_job:
            self.root.after_cancel(self.hide_job)
            self.hide_job = None
        fresh = self.win is None or not self.win.winfo_exists()
        if fresh:
            self._build()
        self.set(text, mood, _fresh=fresh)

    def set(self, text, mood=None, _fresh=False):
        if self.win is None or not self.win.winfo_exists():
            return
        self.text = text
        if mood:
            self.cat.play(mood)
        ax, ay, aw, ah = work_area()
        self._fit(text, ah - self.SIZE - 40)
        self._geometry()
        if _fresh:
            self.sliding = True
            self._slide(self.screen_bottom)
        elif not self.sliding:  # text grew: keep the bottom fixed so the bubble grows upwards
            self.win.geometry(f"{self.w}x{self.h}+{self.x}+{self.y_end}")

    def _slide(self, y):
        if self.win is None or not self.win.winfo_exists():
            return
        y = self.y_end + int((y - self.y_end) * 0.72)  # ease-out towards the (possibly moving) target
        self.win.geometry(f"{self.w}x{self.h}+{self.x}+{y}")
        if abs(y - self.y_end) > 1:
            self.win.after(16, self._slide, y)
        else:
            self.sliding = False
            self.win.geometry(f"{self.w}x{self.h}+{self.x}+{self.y_end}")

    def hide_later(self, ms=700):
        if self.hide_job:
            self.root.after_cancel(self.hide_job)
        self.hide_job = self.root.after(ms, self.hide)

    def hide(self):
        if self.win is None or not self.win.winfo_exists():
            return
        sh = self.win.winfo_screenheight()
        win = self.win
        self.sliding = True

        def down(y):
            if not win.winfo_exists():
                return
            if y >= sh:
                win.destroy()
                self.win = None
                self.sliding = False
                return
            win.geometry(f"{self.w}x{self.h}+{self.x}+{y}")
            win.after(16, down, y + 24)
        down(win.winfo_y())

    @property
    def visible(self):
        return self.win is not None and self.win.winfo_exists()
