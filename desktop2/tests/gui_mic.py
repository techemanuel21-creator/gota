"""Opens the Microfone dialog, runs its test and saves a screenshot. Needs the model file."""
import ctypes
ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
import os, sys, tempfile, traceback
home = tempfile.mkdtemp(); os.environ["GOTA_HOME"] = home; sys.path.insert(0, ".")
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
from gota import store
p = store.Profile(); p.set_name("emanuel", "senhor")
s = store.Settings(); s.set("model_path", os.path.join("models", "gemma4_e2b.litertlm")); s.set("tutorial", True); s.set("cloud_asked", True); s.set("use_cloud", False)
from gota.app import App
from PIL import ImageGrab
app = App()
errors = []
app.report_callback_exception = lambda *a: errors.append("".join(traceback.format_exception(*a)))
state = {"n": 0}


def walk(w):
    yield w
    for c in w.winfo_children():
        yield from walk(c)


def step():
    state["n"] += 1
    if "d" not in state:
        app.attributes("-topmost", True); app.lift()
    app.update()
    if state["n"] >= 5 and hasattr(app, "entry") and app.gemma is not None and "d" not in state:
        app.mic_dialog(); state["d"] = state["n"]
    if "d" in state and state["n"] == state["d"] + 1:
        # press "Testar": find the RoundButton by its text
        for w in walk(app):
            if getattr(w, "text", None) == "Testar":
                w.event_generate("<Button-1>", x=5, y=5); w.event_generate("<ButtonRelease-1>", x=5, y=5)
    if "d" in state and state["n"] > state["d"] + 6:
        app.update(); ImageGrab.grab().save(os.path.join(out, "mic.png"))
        print("ERROS:", errors or "nenhum", flush=True); os._exit(0)
    app.after(1000, step)


app.after(500, step)
app.mainloop()
