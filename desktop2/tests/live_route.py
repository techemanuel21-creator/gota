"""Checks that the model understands what kind of help a free-form sentence asks for (needs the model file)."""
import os, sys, tempfile, time
os.environ["GOTA_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
from gota import brain, store, llm

p = store.Profile(); p.set_name("emanuel", "senhor"); s = store.Settings()
g = llm.Gemma(os.environ.get("GOTA_MODEL") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "gemma4_e2b.litertlm"))
b = brain.Brain(p, s, lambda: g, images=None)
CASES = [
    ("o que está acontecendo na minha tela?", "screen"),
    ("o que tem na minha tela", "screen"),
    ("ó, tem um job no Veeam aí que tá com problema, analisa pra mim", "screen"),
    ("me explica esse erro aqui", "screen"),
    ("dá uma olhada no que eu tô fazendo e me diz se tá certo", "screen"),
    ("esse backup terminou com warning, o que significa?", "screen"),
    ("como eu restauro uma VM no Veeam?", "expert"),
    ("qual a diferença entre NTFS e ReFS?", "expert"),
    ("quanto está o dólar hoje?", "search"),
    ("quem ganhou o jogo ontem?", "search"),
    ("lista os arquivos da pasta downloads", "agent"),
    ("quanto de memória o meu computador está usando?", "agent"),
    ("me conta uma piada", "chat"),
    ("desenha um gato de chapéu", "chat"),
]
b.look_at_screen = lambda *a, **k: "[screen]"
b.agent.run = lambda *a, **k: "[agent]"
def expert(goal, *a, **k):
    print("      consulta ao especialista:", k.get("query") or goal)
    return "[expert]"
b.expert_answer = expert
b.search = lambda *a, **k: ("[search]", None)
b.draw = lambda *a, **k: ("[chat]", None)
b.on_phase = lambda p: None
ok = 0
for text, want in CASES:
    t = time.time()
    out = b.run(text, [], "t")[0]
    got = out if out in ("[screen]", "[agent]", "[expert]", "[search]") else "[chat]"
    ok += got == "[" + want + "]"
    print(f"{'OK  ' if got == '[' + want + ']' else 'FAIL'} {text!r} -> {got} (esperado {want}) {time.time() - t:.1f}s", flush=True)
print(f"{ok}/{len(CASES)}")
hist = [("user", "como eu restauro uma VM no Veeam?"), ("model", "No console do Veeam, abra Home, Backups, escolha a VM e clique em Restore guest files ou Entire VM, senhor.")]
out = b.run("e se eu quiser restaurar só um arquivo dela?", hist, "t2")[0]
print("continuidade ->", out)
