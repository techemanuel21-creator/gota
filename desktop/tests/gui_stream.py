"""Sends a question in the real window and measures when the first text appears versus when the answer is complete. Needs the model files."""
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(1)
import os, sys, tempfile, time, traceback
home = tempfile.mkdtemp(); os.environ["GOTA_HOME"] = home; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from gota import store
p = store.Profile(); p.set_name("emanuel", "senhor")
store.Settings().set("tutorial", True)
from gota.app import App
app = App()
errors = []
app.report_callback_exception = lambda *a: errors.append("".join(traceback.format_exception(*a)))
state = {"n": 0}
QUESTION = sys.argv[1] if len(sys.argv) > 1 else "me explique em quatro frases o que é um snapshot de máquina virtual"


def step():
    state["n"] += 1
    if app.gemma is None or not hasattr(app, "entry") or state["n"] < 3:
        return app.after(1000, step)
    state.setdefault("ready", time.time())
    if "sent" not in state:
        if time.time() - state["ready"] < 45:   # the model warms up in the background, as it would while the user types
            return app.after(1000, step)
        app.entry.set(QUESTION); app.send(); state["sent"] = time.time()
        return app.after(150, step)
    lab = getattr(app, "_live_label", None)
    row = getattr(app, "_live_row", None)
    if "first" not in state and row is not None and row.winfo_exists() and lab is not None and lab.cget("text").strip():
        state["first"] = time.time()
        print(f"PRIMEIRO TEXTO na tela apos {state['first'] - state['sent']:.1f}s: {lab.cget('text')[:70]!r}", flush=True)
    if "last_len" not in state:
        state["last_len"] = 0
    if "first" in state and row is not None and row.winfo_exists():
        state["last_len"] = len(lab.cget("text"))
    cid = app.settings.get("current_chat")
    chat = app.chats.get(cid)
    if chat and len(chat["messages"]) >= 2 and not app.typing:
        total = time.time() - state["sent"]
        print(f"RESPOSTA COMPLETA apos {total:.1f}s | caracteres: {len(chat['messages'][-1]['text'])} | erros: {errors or 'nenhum'}", flush=True)
        print("TEXTO:", chat["messages"][-1]["text"][:300].replace("\n", " ⏎ "), flush=True)
        os._exit(0)
    if time.time() - state["sent"] > 200:
        print("TEMPO ESGOTADO", flush=True); os._exit(1)
    app.after(150, step)


app.after(1000, step); app.mainloop()
