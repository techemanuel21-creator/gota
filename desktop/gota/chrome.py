"""A frameless window with its own title bar: rounded corners (Windows 11), taskbar button, drag, resize, min/max/close."""
import ctypes, tkinter as tk
from pathlib import Path
from ctypes import wintypes

user32, dwm = ctypes.windll.user32, ctypes.windll.dwmapi
user32.GetParent.restype = ctypes.c_void_p
user32.GetParent.argtypes = [ctypes.c_void_p]
user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
dwm.DwmSetWindowAttribute.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]


def hwnd_of(win):
    h = win.winfo_id()
    return user32.GetParent(h) or h


def round_corners(win, border_rgb=None):
    """Rounded corners and an optional coloured hairline border on Windows 11 (silently ignored elsewhere)."""
    try:
        hw = hwnd_of(win)
        pref = ctypes.c_int(2)  # DWMWCP_ROUND
        dwm.DwmSetWindowAttribute(hw, 33, ctypes.byref(pref), 4)
        if border_rgb:
            r, g, b = (int(border_rgb[i:i + 2], 16) for i in (1, 3, 5))
            col = ctypes.c_uint(r | (g << 8) | (b << 16))
            dwm.DwmSetWindowAttribute(hw, 34, ctypes.byref(col), 4)
    except Exception:
        pass


def show_in_taskbar(win):
    """A borderless Tk window has no taskbar button; give it one."""
    try:
        hw = hwnd_of(win)
        style = user32.GetWindowLongW(hw, -20)
        user32.SetWindowLongW(hw, -20, (style & ~0x80) | 0x40000)
        ico = Path(__file__).parent / "assets" / "gota.ico"
        if ico.exists():   # the Gota cat on the taskbar button even when started by pythonw (otherwise Python's icon shows)
            user32.LoadImageW.restype = ctypes.c_void_p
            for kind, size in ((1, 32), (0, 16)):   # ICON_BIG, ICON_SMALL
                h = user32.LoadImageW(None, str(ico), 1, size, size, 0x10)   # IMAGE_ICON, LR_LOADFROMFILE
                if h:
                    user32.SendMessageW(ctypes.c_void_p(hw), 0x80, kind, ctypes.c_void_p(h))   # WM_SETICON
        win.withdraw()
        win.after(15, win.deiconify)
    except Exception:
        pass


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


def work_area(win=None):
    """(x, y, w, h) of the usable area of the monitor that holds `win` (its centre); the primary monitor without a window."""
    rect = wintypes.RECT()
    if win is not None:
        try:
            cx = win.winfo_rootx() + win.winfo_width() // 2
            cy = win.winfo_rooty() + win.winfo_height() // 2
            user32.MonitorFromPoint.restype = wintypes.HANDLE
            user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
            hmon = user32.MonitorFromPoint(wintypes.POINT(cx, cy), 2)  # MONITOR_DEFAULTTONEAREST
            info = _MONITORINFO()
            info.cbSize = ctypes.sizeof(_MONITORINFO)
            user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MONITORINFO)]
            if hmon and user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
                r = info.rcWork
                return r.left, r.top, r.right - r.left, r.bottom - r.top
        except Exception:
            pass
    user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top


class Chrome:
    """Attach to a tk.Tk: removes the native frame and builds the title bar. Put your content in `.body`."""
    BORDER = "#2B3263"

    def __init__(self, win, title, icon_image, colors):
        self.win, self.c = win, colors
        self.maximized = False
        self.restore = None
        win.overrideredirect(True)
        win.configure(bg=self.BORDER)
        self.shell = tk.Frame(win, bg=colors["bg"])
        self.shell.pack(fill="both", expand=True, padx=1, pady=1)
        bar = self.bar = tk.Frame(self.shell, bg=colors["bar"], height=40)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        self.icon = tk.Label(bar, image=icon_image, bg=colors["bar"], bd=0)
        self.icon.pack(side="left", padx=(14, 8))
        self.title = tk.Label(bar, text=title, bg=colors["bar"], fg=colors["muted"], font=("Segoe UI", 10))
        self.title.pack(side="left")
        for glyph, cmd, hover in (("✕", win.quit_app if hasattr(win, "quit_app") else win.destroy, "#E5484D"), ("☐", self.toggle_max, colors["hover"]), ("—", self.minimize, colors["hover"])):
            if glyph == "✕":
                cmd = win.to_tray if hasattr(win, "to_tray") else win.destroy
            b = tk.Label(bar, text=glyph, bg=colors["bar"], fg=colors["text"], font=("Segoe UI", 11), width=5, cursor="hand2")
            b.pack(side="right", fill="y")
            b.bind("<Enter>", lambda e, w=b, h=hover: w.configure(bg=h))
            b.bind("<Leave>", lambda e, w=b: w.configure(bg=colors["bar"]))
            b.bind("<Button-1>", lambda e, c=cmd: c())
            if glyph == "☐":
                self.max_btn = b
        for w in (bar, self.icon, self.title):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._drag)
            w.bind("<Double-Button-1>", lambda e: self.toggle_max())
        self.body = tk.Frame(self.shell, bg=colors["bg"])
        self.body.pack(fill="both", expand=True)
        self._grips()
        win.bind("<Map>", self._on_map)

    # ------------------------------------------------------------------ move / resize
    def _start_drag(self, e):
        self._off = (e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y())

    def _drag(self, e):
        if self.maximized:
            return
        self.win.geometry(f"+{e.x_root - self._off[0]}+{e.y_root - self._off[1]}")

    def _grips(self):
        for side, cursor, where in (("e", "sb_h_double_arrow", dict(relx=1.0, rely=0, relheight=1.0, width=5, anchor="ne", y=40)),
                                    ("s", "sb_v_double_arrow", dict(relx=0, rely=1.0, relwidth=1.0, height=5, anchor="sw")),
                                    ("se", "size_nw_se", dict(relx=1.0, rely=1.0, width=16, height=16, anchor="se"))):
            g = tk.Frame(self.win, cursor=cursor, bg=self.BORDER if side != "se" else self.c["bg"])
            g.place(**where)
            g.lift()
            g.bind("<ButtonPress-1>", lambda e, s=side: self._start_resize(e, s))
            g.bind("<B1-Motion>", lambda e, s=side: self._resize(e, s))
            if side == "se":
                tk.Label(g, text="◢", bg=self.c["bg"], fg=self.c["muted"], font=("Segoe UI", 8), cursor=cursor).place(relx=1, rely=1, anchor="se")

    def _start_resize(self, e, side):
        self._rs = (e.x_root, e.y_root, self.win.winfo_width(), self.win.winfo_height())

    def _resize(self, e, side):
        if self.maximized:
            return
        x0, y0, w0, h0 = self._rs
        w = max(self.win.minsize()[0], w0 + (e.x_root - x0) if "e" in side else w0)
        h = max(self.win.minsize()[1], h0 + (e.y_root - y0) if "s" in side else h0)
        self.win.geometry(f"{w}x{h}")

    # ------------------------------------------------------------------ buttons
    def minimize(self):
        self.win.update_idletasks()
        self.win.overrideredirect(False)
        self.win.iconify()

    def _on_map(self, e):
        if e.widget is self.win and not self.win.overrideredirect() and self.win.state() == "normal":
            self.win.after(20, self._reframe)

    def _reframe(self):
        self.win.overrideredirect(True)
        round_corners(self.win, self.BORDER)
        show_in_taskbar(self.win)

    def toggle_max(self):
        if self.maximized:
            self.win.geometry(self.restore)
            self.max_btn.configure(text="☐")
        else:
            self.restore = self.win.geometry()
            x, y, w, h = work_area(self.win)   # the monitor the window is on, not always the primary one
            self.win.geometry(f"{w}x{h}+{x}+{y}")
            self.max_btn.configure(text="❐")
        self.maximized = not self.maximized
