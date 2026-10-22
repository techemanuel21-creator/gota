"""The coding agent on a tiny task inside a temporary project folder, with the real model. Needs the model files."""
import os, sys, tempfile, time
os.environ["GOTA_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from pathlib import Path
from gota import brain, store, llm, kb, projects

kb.install_seed()
p = store.Profile(); p.set_name("emanuel", "senhor")
g = llm.Gemma(llm.MODEL_FILE)
b = brain.Brain(p, store.Settings(), lambda: g, images=None, on_status=lambda x: print("   [status]", x, flush=True))
asked = []


def confirm(text, danger):
    asked.append(text.split("\n")[0][:90])
    ok = "Permitir que o Gota" in text   # the one-time grant for the project folder; anything else is refused
    print(f"   [permissão] {text.splitlines()[0][:80]} -> {'SIM' if ok else 'não'}", flush=True)
    return ok


b.confirm = confirm
folder = projects.create(tempfile.mkdtemp(prefix="gota_proj_"), "calculadora", "Uma calculadora simples em Python.")
print("projeto:", folder, flush=True)
goal = sys.argv[1] if len(sys.argv) > 1 else "crie o arquivo calc.py com as funções soma e subtracao, crie test_calc.py com testes unittest para elas e rode os testes"
t0 = time.time()
text = b.agent.run_project(goal, folder, [])
print(f"\nTOTAL {time.time() - t0:.0f}s")
print("RESPOSTA:", text[:400].replace("\n", " ⏎ "))
print("ARQUIVOS:", sorted(f.name for f in Path(folder).iterdir() if f.name != ".git"))
for name in ("calc.py", "test_calc.py"):
    f = Path(folder) / name
    print(f"--- {name}:\n" + (f.read_text("utf-8")[:700] if f.exists() else "(não criado)"))
print("PASSOS:", b.agent.last_steps)
print("PERMISSÕES PEDIDAS:", asked)
