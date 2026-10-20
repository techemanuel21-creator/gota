"""Renders the main window in a project chat plus the Projects, Create-project and Chats dialogs, and saves screenshots."""
import ctypes
ctypes.windll.shcore.SetProcessDpiAwareness(1)
import os, sys, tempfile
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
proj_root = Path(tempfile.mkdtemp(prefix="gota_demo_")) / "calculadora"


def shot(name):
    app.update()
    ImageGrab.grab().save(os.path.join(out, name))


def step():
    state["n"] += 1
    if app.gemma is None or not hasattr(app, "entry") or state["n"] < 3:
        return app.after(1000, step)
    if "a" not in state:
        app.attributes("-topmost", True); app.lift()
        folder = projects.create(proj_root.parent, "calculadora", "Uma calculadora simples em Python.")
        (Path(folder) / "calc.py").write_text("def soma(a, b):\n    return a + b\n", "utf-8")
        (Path(folder) / "test_calc.py").write_text("import unittest\n", "utf-8")
        (Path(folder) / "docs").mkdir(); (Path(folder) / "docs" / "guia.md").write_text("# Guia\n", "utf-8")
        import time as _t
        app.brain.agent.bg.extend([
            {"id": 1, "goal": "varredura nos logs do servidor", "status": "rodando", "result": "", "started": _t.time() - 42, "stop": False},
            {"id": 2, "goal": "listar serviços parados", "status": "concluída", "result": "Encontrei 3 serviços parados: Spooler, WSearch e Fax.", "started": _t.time() - 300, "stop": False}])
        chat = app.open_project(folder)
        app.chats.append(chat["id"], "user", "crie calc.py com soma e subtracao e testes, e rode os testes")
        app.chats.append(chat["id"], "gota", "Pronto. Criei **calc.py** e **test_calc.py**; os 2 testes passam (`python -m unittest`).", steps=["write_file  calc.py", "write_file  test_calc.py", "run_command  python -m unittest"])
        other = app.chats.create(); app.chats.append(other["id"], "user", "bom dia"); app.chats.set_title(other["id"], "Saudação")
        app.open_chat(chat["id"]); state["a"] = 1
        return app.after(1800, step)
    if "b" not in state:
        shot("1_projeto.png"); app.projects_dialog(); state["b"] = 1
        return app.after(1500, step)
    if "c" not in state:
        shot("2_projetos.png")
        for w in app.winfo_children():
            if w.winfo_class() == "Toplevel": w.destroy()
        app.create_project_dialog(); state["c"] = 1
        return app.after(1500, step)
    if "d" not in state:
        shot("3_criar.png")
        for w in app.winfo_children():
            if w.winfo_class() == "Toplevel": w.destroy()
        app.chats_dialog(); state["d"] = 1
        return app.after(1500, step)
    shot("4_conversas.png")
    print("OK", flush=True)
    os._exit(0)


app.after(1000, step); app.after(200000, lambda: os._exit(1)); app.mainloop()
