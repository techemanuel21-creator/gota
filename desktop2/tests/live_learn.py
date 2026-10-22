"""Gota does not know a library: it must find the official documentation on the internet, keep it, and answer from it (model + internet needed)."""
import os, sys, tempfile, time
os.environ["GOTA_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from gota import brain, store, llm, kb

kb.install_seed()
p = store.Profile(); p.set_name("emanuel", "senhor")
g = llm.Gemma(llm.MODEL_FILE)
b = brain.Brain(p, store.Settings(), lambda: g, images=None, on_status=lambda x: print("   [status]", x, flush=True))
topic = sys.argv[1] if len(sys.argv) > 1 else "biblioteca Python rich para mostrar tabelas coloridas no terminal"
question = sys.argv[2] if len(sys.argv) > 2 else "como crio uma tabela com a biblioteca rich do Python?"
print("antes — a base já cobre?", kb.good_enough(kb.search(topic, 3), topic), flush=True)
t = time.time()
saved = b.learn_topic(topic)
print(f"aprendeu {len(saved)} página(s) em {time.time() - t:.0f}s:", [s[:60] for s in saved], flush=True)
for score, title, src, text in kb.search(question, 2):
    print(f"   hit {score:.1f} | {title[:60]} | {src[:70]} | código: {'```' in text}", flush=True)
t = time.time()
answer = b.expert_answer(question)
print(f"\nRESPOSTA ({time.time() - t:.0f}s):\n{answer}")
print("\nnotas na base agora:", [n for n in kb.listing() if "rich" in n][:6])
