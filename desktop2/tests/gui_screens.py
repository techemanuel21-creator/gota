"""Opens the Telas dialog and saves a screenshot. Needs the model file."""
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
    if app.gemma is None or not hasattr(app, "entry") or state["n"] < 3:
        return app.after(1000, step)
    if "d" not in state:
        app.attributes("-topmost", True); app.lift(); app.screens_dialog(); state["d"] = 1
        return app.after(2000, step)
    app.update()
    ImageGrab.grab().save(os.path.join(out, "screens.png"))
    print("ERROS:", errors or "nenhum", flush=True)
    os._exit(0)
app.after(500, step)
app.mainloop()
