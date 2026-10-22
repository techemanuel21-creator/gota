"""Opens a chat that has an image reply (like after 'crie uma imagem...') and saves a screenshot. Needs the model file."""
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(1)
import os, sys, tempfile, traceback
home = tempfile.mkdtemp(); os.environ["GOTA_HOME"] = home; sys.path.insert(0, ".")
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
from gota import store
p = store.Profile(); p.set_name("emanuel", "senhor")
store.Settings().set("model_path", os.environ.get("GOTA_MODEL") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "gemma4_e2b.litertlm"))
store.Settings().set("tutorial", True)
from gota.app import App
from PIL import ImageGrab
app = App()
errors = []
app.report_callback_exception = lambda *a: errors.append("".join(traceback.format_exception(*a)))
state = {"n": 0}


def shot(name):
    app.update(); x, y, w, h = app.winfo_rootx(), app.winfo_rooty(), app.winfo_width(), app.winfo_height()
    ImageGrab.grab((x, y, x + w, y + h)).save(os.path.join(out, name))


def step():
    state["n"] += 1
    if app.gemma is None or not hasattr(app, "entry") or state["n"] < 3:
        return app.after(1000, step)
    if "opened" not in state:
        c = app.chats.create()
        app.chats.append(c["id"], "user", "crie uma imagem de um gato em um telhado")
        app.chats.append(c["id"], "gota", "Aqui está, senhor.", r"C:\Users\Emanuel\Pictures\GOTA IA\gota_1792471373.jpg")
        app.open_chat(c["id"]); state["opened"] = 1
        return app.after(2500, step)
    shot("image_chat.png")
    print("ERROS:", errors or "nenhum", flush=True)
    os._exit(0)


app.after(1000, step); app.after(300000, lambda: os._exit(1)); app.mainloop()
