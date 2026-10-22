"""The WhatsApp message must be written in the owner's voice, use the conversation, and accept a spoken correction. Needs the model files."""
import os, sys, tempfile
os.environ["GOTA_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from gota import brain, store, llm

p = store.Profile(); p.set_name("emanuel", "senhor")
g = llm.Gemma(llm.MODEL_FILE)
b = brain.Brain(p, store.Settings(), lambda: g, images=None)
b.on_phase = lambda x: None
b.whatsapp.connected = lambda: True
sent = []
b.whatsapp.send = lambda contact, message="", image=None, confirm=lambda f: True, on_status=lambda s: None, dry_run=False: (confirm(contact), sent.append((contact, message)), contact)[2]
shown = []
b.confirm_message = lambda found, requested, message, extra="": (shown.append(message), (True, None))[1]

hist = []
for turn in ("mande uma mensagem para o Alex T2W no whatsapp se apresentando",
             "não explique que você é o gota e o que você faz, só me apresente pelo nome",
             "pode mandar mais curto, só um oi e o meu nome"):
    sent.clear(); shown.clear()
    out = b.run(turn, list(hist), "wa")[0]
    print(f"\n> {turn}\n  resposta: {out[:140]}\n  mensagem preparada: {shown or sent}", flush=True)
    hist += [("user", turn), ("model", out)]
