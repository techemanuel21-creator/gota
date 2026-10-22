"""Real tasks through the agent and the expert mode with the real model (needs the model file and internet)."""
import os, sys, tempfile, time
os.environ["GOTA_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
from gota import brain, store, llm, kb

kb.install_seed()
p = store.Profile(); p.set_name("emanuel", "senhor"); s = store.Settings()
g = llm.Gemma(os.environ.get("GOTA_MODEL") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "gemma4_e2b.litertlm"))
b = brain.Brain(p, s, lambda: g, images=None, on_status=lambda x: print("   [status]", x, flush=True))
b.confirm = lambda text, danger: (print("   [CONFIRMAÇÃO PEDIDA]", text.replace("\n", " | ")[:140], "-> negada no teste", flush=True), False)[1]
for q in sys.argv[1:]:
    t = time.time()
    text, _ = b.run(q, [], "t")
    print(f"\n> {q}\n  {text}\n  ({time.time() - t:.0f}s)\n", flush=True)
print("base agora:", kb.listing())
