"""With two (simulated) screens, does the model pick the screen the user means, from free-form sentences? (needs the model file)"""
import os, sys, tempfile
os.environ["GOTA_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
from gota import brain, store, llm, tools

p = store.Profile(); p.set_name("emanuel", "senhor"); s = store.Settings()
g = llm.Gemma(os.environ.get("GOTA_MODEL") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "gemma4_e2b.litertlm"))
b = brain.Brain(p, s, lambda: g, images=None)
MONS = [{"n": 1, "rect": (0, 0, 1920, 1080), "primary": True, "where": "principal"},
        {"n": 2, "rect": (1920, 0, 3840, 1080), "primary": False, "where": "à direita da principal"}]
tools.monitors = lambda: MONS
tools.cursor_monitor = lambda m: MONS[0]
seen = []
b.look_at_screen = lambda goal, spoken=False, history=(), screen=None: (seen.append(screen), "[screen]")[1]
b.agent.run = lambda *a, **k: "[agent]"
b.expert_answer = lambda *a, **k: "[expert]"
b.search = lambda *a, **k: ("[search]", None)
b.on_phase = lambda p: None
CASES = [("analisa a tela 2 e vê o que está acontecendo", "2"),
         ("o que tem no segundo monitor?", "2"),
         ("dá uma olhada na tela da direita", "2"),
         ("o que tem na minha tela", "None"),
         ("olha a primeira tela e me diz se tem algum erro", "1"),
         ("vê o que tá rolando nas duas telas", "all"),
         ("e no outro monitor, o que tá aparecendo?", "2")]
ok = 0
for text, want in CASES:
    seen.clear()
    out = b.run(text, [], "t")[0]
    got = str(seen[0]) if seen else out
    ok += got == want
    print(f"{'OK  ' if got == want else 'FAIL'} {text!r} -> screen={got} (esperado {want})", flush=True)
print(f"{ok}/{len(CASES)}")
