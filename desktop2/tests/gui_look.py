"""Renders the chat window with a sample conversation (code block, agent actions card, status line) and saves screenshots."""
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(1)
import os, sys, tempfile, traceback
home = tempfile.mkdtemp(); os.environ["GOTA_HOME"] = home; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
from gota import store
p = store.Profile(); p.set_name("emanuel", "senhor")
store.Settings().set("tutorial", True)
from gota.app import App
from PIL import ImageGrab
app = App()
errors = []
pass
state = {"n": 0}


def shot(name):
    app.update(); x, y, w, h = app.winfo_rootx(), app.winfo_rooty(), app.winfo_width(), app.winfo_height()
    ImageGrab.grab((x, y, x + w, y + h)).save(os.path.join(out, name))


def step():
    state["n"] += 1
    if app.gemma is None or not hasattr(app, "entry") or state["n"] < 3:
        return app.after(1000, step)
    if "a" not in state:
        app.attributes("-topmost", True); app.lift()
        c = app.chats.create()
        app.chats.append(c["id"], "user", "como listo os serviços em execução no PowerShell?")
        app.chats.append(c["id"], "gota", "Para listar só os serviços em execução, use o comando abaixo, senhor:\n```powershell\nGet-Service | Where-Object Status -eq Running | Sort-Object DisplayName\n```\nSe quiser guardar o resultado num arquivo, acrescente `| Out-File servicos.txt` ao final.")
        app.chats.append(c["id"], "user", "agora veja quais pastas existem em C:\\projeto pessoal e me diga o tamanho de cada uma")
        app.chats.append(c["id"], "gota", "Em C:\\projeto pessoal há duas pastas de projeto: **desktop** (8,7 GB, com os modelos) e **mobile** (2,9 GB, o app Android).", steps=["list_dir  C:\\projeto pessoal", "run_command  Get-ChildItem -Recurse | Measure-Object Length -Sum", "final"])
        app.chats.get(c["id"])
        app.chats.set_title(c["id"], "Listar serviços do PowerShell")
        app.open_chat(c["id"]); state["a"] = 1
        return app.after(1800, step)
    if "b" not in state:
        app.entry.set("Escreva aqui…"); app.set_activity("Pensando…"); state["b"] = 1
        return app.after(2300, step)
    shot("look.png")
    print("ERROS:", errors or "nenhum", flush=True)
    os._exit(0)


app.after(1000, step); app.after(200000, lambda: os._exit(1)); app.mainloop()
