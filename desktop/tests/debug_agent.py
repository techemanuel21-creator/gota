import os, sys, tempfile
os.environ["GOTA_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
from gota import brain, store, llm
p = store.Profile(); p.set_name("emanuel", "senhor"); s = store.Settings()
g = llm.Gemma(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "gemma4_e2b.litertlm"))
b = brain.Brain(p, s, lambda: g, images=None)
orig = g.chat
def spy(*a, **k):
    r = orig(*a, **k)
    print("USER>", a[3][:200].replace("\n", " "), "\nMODEL>", r[:400].replace("\n", " "), "\n", flush=True)
    return r
g.chat = spy
print("FINAL:", b.agent.run(sys.argv[1], []))
