# PyInstaller recipe: build with  pyinstaller Gota.spec --noconfirm
from PyInstaller.utils.hooks import collect_all
datas, binaries, hidden = [("gota/assets", "gota/assets")], [], ["pystray._win32", "pyttsx3.drivers", "pyttsx3.drivers.sapi5"]
for pkg in ("litert_lm", "litert_lm_api", "piper", "vosk", "executorch", "onnxruntime", "sounddevice", "_sounddevice_data", "pyttsx3"):
    try:
        d, b, h = collect_all(pkg); datas += d; binaries += b; hidden += h
    except Exception:
        pass
a = Analysis(["main.py"], datas=datas, binaries=binaries, hiddenimports=hidden, excludes=["tkinter.test", "torchvision", "torchaudio", "matplotlib"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Gota", console=False, icon=None)
coll = COLLECT(exe, a.binaries, a.datas, name="Gota")
