"""Types a message and presses send in the real window; checks the message bubble and the thinking row appear. Needs the model file."""
import ctypes
ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
import os, sys, tempfile, time, traceback
home = tempfile.mkdtemp(); os.environ["GOTA_HOME"] = home; sys.path.insert(0, ".")
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
from gota import store
p = store.Profile(); p.set_name("emanuel", "senhor")
s = store.Settings(); s.set("model_path", os.path.join("models", "gemma4_e2b.litertlm")); s.set("tutorial", True); s.set("cloud_asked", True); s.set("use_cloud", bool(os.environ.get("OPENROUTER_API_KEY")))
from gota.app import App
from PIL import ImageGrab
app = App()
errors = []
app.report_callback_exception = lambda *a: errors.append("".join(traceback.format_exception(*a)))
state = {"n": 0}
MSG = open(sys.argv[2], encoding="utf-8-sig").read().strip() if len(sys.argv) > 2 else "oi, tudo bem?"


def step():
    state["n"] += 1
    app.update()
    if app.gemma is None or not hasattr(app, "entry") or state["n"] < 3:
        return app.after(1000, step)
    if "sent" not in state:
        app.attributes("-topmost", True); app.lift(); app.geometry("1097x687+40+10"); app.update()
        app.entry.set(MSG); app.send(); state["sent"] = state["n"]
        return app.after(1000, step)
    if state["n"] >= state["sent"] + int(os.environ.get("WAIT", "3")):
        kids = [(type(w).__name__, w.winfo_height(), w.winfo_ismapped()) for w in app.msgs.winfo_children()]
        print("yview:", app.scroll.yview(), "bbox:", app.scroll.bbox("all"), "canvas h:", app.scroll.winfo_height(), "msgs h:", app.msgs.winfo_height(), "msgs children:", kids, "| scrollregion:", app.scroll.cget("scrollregion"), flush=True)
        ImageGrab.grab().save(os.path.join(out, "send.png"))
        print("ERROS:", errors or "nenhum", flush=True)
        os._exit(0)
    app.after(1000, step)


app.after(500, step)
app.mainloop()
