"""Real questions through the brain with the real model. Run from the desktop folder; needs the model file."""
import os, sys, tempfile, time
os.environ["GOTA_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
from gota import brain, store, llm

p = store.Profile(); p.set_name("emanuel", "senhor"); s = store.Settings()
g = llm.Gemma(os.environ.get("GOTA_MODEL") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "gemma4_e2b.litertlm"))
b = brain.Brain(p, s, lambda: g, images=None, on_status=lambda x: print("   [status]", x))
hist = []
questions = sys.argv[1:] or ["o fim da escala seis por um já foi aprovado?", "quanto custa o ingresso do cinema aqui?"]
for q in questions:
    t = time.time()
    text, img = b.run(q, hist, "c1")
    print(f"> {q}\n  {text}   ({time.time() - t:.1f}s)")
    hist += [("user", q), ("model", text)]
