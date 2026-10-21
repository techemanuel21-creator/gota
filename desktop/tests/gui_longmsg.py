"""A long user message in the real window: folded with 'Ler mais', then expanded. Saves two screenshots. Needs the model file."""
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
MSG = open(sys.argv[2], encoding="utf-8-sig").read().strip()


def walk(w):
    yield w
    for c in w.winfo_children():
        yield from walk(c)


def step():
    state["n"] += 1
    app.update()
    if app.gemma is None or not hasattr(app, "entry") or state["n"] < 3:
        return app.after(1000, step)
    if "d" not in state:
        app.attributes("-topmost", True); app.lift(); app.geometry("1097x687+40+10")
        for w in app.msgs.winfo_children():
            w.destroy()
        app.add_message("user", MSG)
        app.add_message("gota", "Pois não, senhor. Segue o script.")
        state["d"] = state["n"]
        return app.after(1200, step)
    if "shot1" not in state:
        ImageGrab.grab().save(os.path.join(out, "folded.png")); state["shot1"] = 1
        for w in walk(app.msgs):
            if hasattr(w, "toggle"):
                w.toggle()
        return app.after(1200, step)
    ImageGrab.grab().save(os.path.join(out, "expanded.png"))
    print("ERROS:", errors or "nenhum", flush=True)
    os._exit(0)


app.after(500, step)
app.mainloop()
