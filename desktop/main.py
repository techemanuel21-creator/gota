"""Gota Local Assistant for Windows."""
import ctypes, sys

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)  # sharp text on high-DPI screens
except Exception:
    pass

if __name__ == "__main__":
    # one copy at a time: a second launch just brings the first one back is not possible without a server, so refuse politely
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "GotaLocalAssistantSingleton")
    if ctypes.windll.kernel32.GetLastError() == 183:
        ctypes.windll.user32.MessageBoxW(None, "O Gota já está aberto (veja o ícone perto do relógio).", "Gota", 0x40)
        sys.exit(0)
    from gota.app import App
    App().mainloop()
