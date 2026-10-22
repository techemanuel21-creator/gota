"""In the real window, coding mode: opens a new project, asks opencode's build agent for code with a test, then uses the "/" commands; checks the files, the steps card,
the stored chat and the session that is kept for the chat."""
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
state = {"n": 0, "asked": []}
SEQ = ["crie calc.py com a função soma(a, b) e test_calc.py com um teste pytest; rode o teste e me diga o resultado", "rode o comando whoami e me diga o usuário", "/diff", "/desfazer", "/ajuda"]


def shot(name):
    app.update(); time.sleep(0.8); app.update()
    x, y, w, h = app.winfo_rootx(), app.winfo_rooty(), app.winfo_width(), app.winfo_height()
    ImageGrab.grab((x, y, x + w, y + h)).save(os.path.join(out, name))


def confirm(text, danger):
    state["asked"].append(text.split("\n\n")[1] if "\n\n" in text else text)
    return True


def step():
    state["n"] += 1
    if app.gemma is None or not hasattr(app, "entry") or state["n"] < 3:
        return app.after(1000, step)
    if "opened" not in state:
        app.brain.confirm = confirm
        folder = projects.create(tempfile.mkdtemp(prefix="gota_coder_"), "calculadora", "Uma calculadora simples.")
        app.open_project(folder); state["folder"] = Path(folder); state["opened"] = 1; state["i"] = 0
        return app.after(2000, step)
    cid = app.settings.get("current_chat")
    chat = app.chats.get(cid)
    i = state["i"]
    if "sent" not in state:
        app.entry.set(SEQ[i]); app.send(); state["sent"] = time.time(); state["want"] = len(chat["messages"]) + 1 + 1
        return app.after(1000, step)
    if len(chat["messages"]) >= state["want"] and not app.typing:
        reply = chat["messages"][-1]
        print(f"[{SEQ[i][:30]!r}] {time.time() - state['sent']:.0f}s | passos: {reply.get('steps')}\n   RESPOSTA: {reply['text'][:240]!r}", flush=True)
        shot(f"coder_{i}.png")
        state["i"] += 1; state.pop("sent")
        if state["i"] >= len(SEQ):
            f = state["folder"]
            print("ARQUIVOS:", sorted(x.name for x in f.iterdir() if not x.name.startswith(".")))
            print("SESSAO GUARDADA NO CHAT:", bool(app.chats.get(cid).get("oc_session")), "| permissões pedidas:", state["asked"][:3])
            sys.stdout.flush(); os._exit(0)
        return app.after(500, step)
    if time.time() - state["sent"] > 300:
        print("TEMPO ESGOTADO"); os._exit(1)
    app.after(1500, step)


app.after(1000, step); app.mainloop()


