"""The coding agent EDITING an existing project (read, edit_file, test), with the real model. Needs the model files."""
import os, sys, tempfile, time
os.environ["GOTA_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from pathlib import Path
from gota import brain, store, llm, kb

kb.install_seed()
p = store.Profile(); p.set_name("emanuel", "senhor")
g = llm.Gemma(llm.MODEL_FILE)
b = brain.Brain(p, store.Settings(), lambda: g, images=None, on_status=lambda x: print("   [status]", x, flush=True))
b.confirm = lambda text, danger: (print(f"   [permissão] {text.splitlines()[0][:80]} -> {'SIM' if 'Permitir que o Gota' in text else 'não'}", flush=True), "Permitir que o Gota" in text)[1]

folder = Path(tempfile.mkdtemp(prefix="gota_imp_")) / "calc-existente"
folder.mkdir(parents=True)
(folder / "calc.py").write_text("def soma(a, b):\n    return a + b\n\n\ndef subtracao(a, b):\n    return a - b\n", "utf-8")
(folder / "test_calc.py").write_text(
    "import unittest\nfrom calc import soma, subtracao\n\n\nclass T(unittest.TestCase):\n    def test_soma(self):\n        self.assertEqual(soma(2, 3), 5)\n\n"
    "    def test_subtracao(self):\n        self.assertEqual(subtracao(5, 2), 3)\n\n\nif __name__ == '__main__':\n    unittest.main()\n", "utf-8")
goal = sys.argv[1] if len(sys.argv) > 1 else "adicione a função multiplicacao em calc.py e um teste para ela em test_calc.py, depois rode os testes"
t0 = time.time()
text = b.agent.run_project(goal, folder, [])
print(f"\nTOTAL {time.time() - t0:.0f}s")
print("RESPOSTA:", text[:400].replace("\n", " ⏎ "))
for name in ("calc.py", "test_calc.py"):
    print(f"--- {name}:\n" + (folder / name).read_text("utf-8"))
print("PASSOS:", b.agent.last_steps)
import subprocess
r = subprocess.run([sys.executable, "-m", "unittest"], cwd=folder, capture_output=True, text=True)
print("TESTES RODADOS POR MIM:", "OK" if r.returncode == 0 else "FALHARAM", "|", r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "")
