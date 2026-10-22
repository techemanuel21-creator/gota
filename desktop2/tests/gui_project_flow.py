"""In the real window: opens a new project, types a coding request, waits for the agent to finish, and checks the file, the steps card and the stored chat."""
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(1)
import os, sys, tempfile, time
home = tempfile.mkdtemp(); os.environ["GOTA_HOME"] = home; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
from pathlib import Path
from gota import store, projects
p = store.Profile(); p.set_name("emanuel", "senhor")
store.Settings().set("tutorial", True)
from gota.app import App
from PIL import ImageGrab
app = App()
state = {"n": 0}


def step():
    state["n"] += 1
    if app.gemma is None or not hasattr(app, "entry") or state["n"] < 3:
        return app.after(1000, step)
    state.setdefault("ready", time.time())
    if "opened" not in state:
        app.brain.confirm = lambda text, danger: "Permitir que o Gota" in text   # the one-time folder grant; anything else is refused
        folder = projects.create(tempfile.mkdtemp(prefix="gota_flow_"), "ola-mundo", "Programa que diz olá.")
        app.open_project(folder); state["folder"] = Path(folder); state["opened"] = 1
        return app.after(50000, step)   # let the model warm up in the background, as it would while the user types
    if "sent" not in state:
        app.entry.set("crie o arquivo ola.py que imprime Olá, mundo! e rode ele"); app.send(); state["sent"] = time.time()
        return app.after(1000, step)
    cid = app.settings.get("current_chat")
    chat = app.chats.get(cid)
    if len(chat["messages"]) >= 2 and not app.typing:
        app.update(); time.sleep(1.0)
        app.update(); x, y, w, h = app.winfo_rootx(), app.winfo_rooty(), app.winfo_width(), app.winfo_height()
        ImageGrab.grab((x, y, x + w, y + h)).save(os.path.join(out, "flow.png"))
        reply = chat["messages"][-1]
        f = state["folder"] / "ola.py"
        print(f"TEMPO {time.time() - state['sent']:.0f}s | arquivo criado: {f.exists()} | passos guardados: {reply.get('steps')}")
        print("RESPOSTA:", reply["text"][:300].replace("\n", " ⏎ "))
        print("CONTEÚDO:", f.read_text('utf-8')[:200] if f.exists() else None)
        os._exit(0)
    if time.time() - state["sent"] > 400:
        print("TEMPO ESGOTADO"); os._exit(1)
    app.after(1500, step)


app.after(1000, step); app.mainloop()
