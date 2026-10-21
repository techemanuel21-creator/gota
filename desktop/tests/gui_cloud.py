"""First-use cloud key screen and the Nuvem dialog: screenshots."""
import ctypes
ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
import os, sys, tempfile, traceback
home = tempfile.mkdtemp(); os.environ["GOTA_HOME"] = home; sys.path.insert(0, ".")
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
from gota import store
p = store.Profile(); p.set_name("emanuel", "senhor")
store.Settings().set("model_path", os.path.join("models", "gemma4_e2b.litertlm")); store.Settings().set("tutorial", True)
from gota.app import App
from PIL import ImageGrab
app = App()
errors = []
app.report_callback_exception = lambda *a: errors.append("".join(traceback.format_exception(*a)))
state = {"n": 0}


def step():
    state["n"] += 1
    if "d" not in state:
        app.attributes("-topmost", True); app.lift()
    app.update()
    if state["n"] == 3:
        ImageGrab.grab().save(os.path.join(out, "cloud_setup.png"))
        app.settings.set("cloud_asked", True); app.show_boot()
    if state["n"] >= 6 and hasattr(app, "entry") and app.gemma is not None and "d" not in state:
        try:
            app.cloud_dialog()
        except Exception:
            traceback.print_exc()
        print("toplevels:", [w.winfo_ismapped() for w in app.winfo_children() if w.winfo_class() == "Toplevel"], flush=True)
        state["d"] = state["n"]
    if "d" in state and state["n"] > state["d"] + 5:
        app.update(); print("tops:", [(w.winfo_geometry(), w.winfo_ismapped(), w.winfo_viewable()) for w in app.winfo_children() if w.winfo_class() == "Toplevel"], flush=True); ImageGrab.grab().save(os.path.join(out, "cloud_dialog.png"))
        print("ERROS:", errors or "nenhum", flush=True); os._exit(0)
    app.after(1000, step)


app.after(500, step)
app.mainloop()
