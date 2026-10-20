"""Opens the real window, sends a message, waits for the answer and saves screenshots. Needs the model file."""
import os, sys, tempfile, time
home = tempfile.mkdtemp(); os.environ["GOTA_HOME"] = home; sys.path.insert(0, ".")
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
from gota import store
p = store.Profile(); p.set_name("emanuel", "senhor")
store.Settings().set("model_path", os.environ.get("GOTA_MODEL") or r"C:\projeto pessoal\.tools\gemma4_e2b.litertlm")
store.Settings().set("tutorial", True)
from gota.app import App
from PIL import ImageGrab
app = App()
def shot(name):
    app.update(); x, y, w, h = app.winfo_rootx(), app.winfo_rooty(), app.winfo_width(), app.winfo_height()
    ImageGrab.grab((x, y, x + w, y + h)).save(os.path.join(out, name))
state = {"n": 0}
def step():
    state["n"] += 1
    if app.gemma is None: return app.after(1000, step)
    if state["n"] < 3 or not hasattr(app, "entry"): return app.after(1000, step)
    if "sent" not in state:
        shot("1_chat.png"); app.entry.insert("1.0", "bom dia"); app.send(); state["sent"] = 1; return app.after(1500, step)
    if "sent2" not in state and not app.thinking.winfo_exists():
        shot("2_greeting.png"); app.entry.insert("1.0", "por que o céu é azul?"); app.send(); state["sent2"] = 1; return app.after(3000, step)
    if "sent2" in state and not app.thinking.winfo_exists():
        shot("3_answer.png"); app.summon_test = 1
        app.overlay.show("Pois não, senhor?", "anim_cat_listen"); app.after(1200, lambda: (ImageGrab.grab().save(os.path.join(out, "4_overlay.png")), os._exit(0)))
        return
    app.after(1000, step)
app.after(1000, step); app.after(240000, lambda: os._exit(1)); app.mainloop()
