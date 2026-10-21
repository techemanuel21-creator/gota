# PyInstaller recipe: build with  pyinstaller Gota.spec --noconfirm
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs, collect_submodules
datas, binaries, hidden = [("gota/assets", "gota/assets"), ("gota/seed", "gota/seed"), ("gota/skills", "gota/skills"), ("vscode-extension", "vscode-extension")], [], ["pystray._win32", "pyttsx3.drivers", "pyttsx3.drivers.sapi5"]
for pkg in ("litert_lm", "litert_lm_api", "piper", "vosk", "onnxruntime", "sounddevice", "_sounddevice_data", "pyttsx3", "faster_whisper", "ctranslate2", "tokenizers", "av", "pypdf", "openpyxl", "docx", "fpdf", "psutil", "playwright", "msal", "greenlet", "pyee", "msal_extensions", "parselmouth"):
    try:
        d, b, h = collect_all(pkg); datas += d; binaries += b; hidden += h
    except Exception:
        pass
try:  # executorch: skip devtools (its visualiser imports a package we do not ship and aborts the build)
    hidden += collect_submodules("executorch", filter=lambda n: "devtools" not in n and "examples" not in n and "test" not in n)
    datas += collect_data_files("executorch"); binaries += collect_dynamic_libs("executorch")
    hidden += ["executorch.extension.pybindings._C", "executorch.extension.pybindings.data_loader", "executorch.extension.pybindings.portable_lib"]
    import glob, os, importlib.util
    root = list(importlib.util.find_spec("executorch").submodule_search_locations)[0]
    for f in glob.glob(os.path.join(root, "**", "*.pyd"), recursive=True):
        rel = os.path.relpath(os.path.dirname(f), root)
        binaries.append((f, "executorch" if rel == "." else os.path.join("executorch", rel)))
except Exception:
    pass
a = Analysis(["main.py"], datas=datas, binaries=binaries, hiddenimports=hidden, excludes=["executorch.devtools", "model_explorer", "tkinter.test", "torchvision", "torchaudio", "matplotlib"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Gota", console=False, icon="gota/assets/gota.ico")
coll = COLLECT(exe, a.binaries, a.datas, name="Gota")
