"""Times every model call of one agent task (plan, each step, final check) with its input size. Needs the model files."""
import os, sys, tempfile, time
os.environ["GOTA_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from gota import brain, store, llm, kb

kb.install_seed()
p = store.Profile(); p.set_name("emanuel", "senhor")
g = llm.Gemma(llm.MODEL_FILE)
b = brain.Brain(p, store.Settings(), lambda: g, images=None, on_status=lambda x: print("   [status]", x, flush=True))
b.confirm = lambda text, danger: (print("   [CONFIRMAÇÃO]", text.replace("\n", " | ")[:110], "-> negada", flush=True), False)[1]
calls = []
_chat, _one = g.chat, g.one_shot


def chat(key, system, history, user_text, *a, **k):
    t = time.time(); r = _chat(key, system, history, user_text, *a, **k)
    calls.append(("passo", len(user_text), len(r), time.time() - t)); print(f"   [modelo] passo: entrada {len(user_text)} chars, saída {len(r)} chars, {time.time() - t:.1f}s", flush=True)
    return r


def one_shot(system, user_text, *a, **k):
    t = time.time(); r = _one(system, user_text, *a, **k)
    calls.append(("avulsa", len(system) + len(user_text), len(r), time.time() - t)); print(f"   [modelo] avulsa: entrada {len(system) + len(user_text)} chars, saída {len(r)} chars, {time.time() - t:.1f}s", flush=True)
    return r


g.chat, g.one_shot = chat, one_shot
goal = sys.argv[1] if len(sys.argv) > 1 else "analise a pasta gota deste projeto e me diga quais são os módulos principais e o que cada um faz"
t0 = time.time()
text = b.agent.run(goal, [])
total = time.time() - t0
print(f"\nTOTAL {total:.0f}s | chamadas: {len(calls)} | tempo no modelo: {sum(c[3] for c in calls):.0f}s")
print("RESPOSTA:", text[:300].replace("\n", " ⏎ "))
