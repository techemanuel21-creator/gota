"""Renders a message with a code block, then sends a real question and waits for the automatic chat title. Needs the model file."""
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(1)
import os, sys, tempfile, time, traceback
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
state = {"n": 0, "t0": None}


def shot(name):
    app.update(); x, y, w, h = app.winfo_rootx(), app.winfo_rooty(), app.winfo_width(), app.winfo_height()
    ImageGrab.grab((x, y, x + w, y + h)).save(os.path.join(out, name))


def step():
    state["n"] += 1
    if app.gemma is None or not hasattr(app, "entry") or state["n"] < 3:
        return app.after(1000, step)
    if "ready_t" not in state:
        state["ready_t"] = time.time()
    if "static" not in state:
        c = app.chats.create()
        app.chats.append(c["id"], "user", "como listo os serviços em execução?")
        app.chats.append(c["id"], "gota", "Use o PowerShell, senhor. Este comando mostra só os serviços **em execução**:\n```powershell\nGet-Service | Where-Object Status -eq Running | Sort-Object DisplayName\n```\nSe preferir o prompt de comando:\n```cmd\nnet start\n```\nPosso também exportar a lista para um arquivo, se desejar.")
        app.open_chat(c["id"]); state["static"] = 1
        return app.after(2500, step)
    if "shot1" not in state:
        shot("1_code.png"); state["shot1"] = 1
        app.new_chat() if hasattr(app, "new_chat") else None
        return app.after(1500, step)
    if "sent" not in state:
        if time.time() - state["ready_t"] < 50:   # let the background warm-up finish, as it would while the user types
            return app.after(1500, step)
        app.entry.set("como eu listo os serviços em execução no PowerShell?"); app.send(); state["sent"] = 1; state["t0"] = time.time()
        return app.after(3000, step)
    cid = app.settings.get("current_chat")
    chat = app.chats.get(cid)
    done = chat and len(chat["messages"]) >= 2 and not app.typing
    if done and "answered" not in state:
        state["answered"] = time.time()
    titled = chat and chat["title"] != "Nova conversa"
    if (done and titled) or time.time() - state["t0"] > 240:
        app.update(); time.sleep(1.0); shot("2_typed.png")
        print("TEMPO ate a resposta:", round(state.get("answered", time.time()) - state["t0"], 1), "s", flush=True)
        print("TITULO:", chat["title"], "| mensagens:", len(chat["messages"]), "| ERROS:", errors or "nenhum", flush=True)
        print("RESPOSTA:", chat["messages"][-1]["text"][:400].replace("\n", " ⏎ "), flush=True)
        os._exit(0)
    app.after(1500, step)


app.after(1000, step); app.after(420000, lambda: os._exit(1)); app.mainloop()
