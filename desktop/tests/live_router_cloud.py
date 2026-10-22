"""Which action does the router pick, and how fast? (real cloud model; the actions themselves are not executed)"""
import os, sys, tempfile, time
os.environ["GOTA_HOME"] = tempfile.mkdtemp(); sys.path.insert(0, ".")
from gota import sdk
g = sdk.Gota(confirm=lambda t, d=False: True)
g.settings.set("cloud_model", os.environ.get("GOTA_CLOUD_MODEL", ""))
b = g.brain
b.whatsapp.connected = lambda: True
b.whatsapp.unread = lambda s=None: [{"title": "Maria", "count": 2}]
picked = []
def fake_act(d, goal, lower, image, asked):
    picked.append(d.get("action")); return f"[{d.get('action')}]", None
b.act = fake_act
CASES = [("quantas conversas não lidas eu tenho no whatsapp?", "whatsapp_unread"), ("qual a minha agenda amanhã?", "outlook"), ("tenho e-mails não lidos?", "outlook"),
         ("abre o chrome", "open_app"), ("manda um print da tela 2 pro João", "whatsapp_send"), ("o que é RAID 5?", "ask_expert|reply"), ("analisa o erro que está na tela", "look_at_screen"),
         ("liste os arquivos da pasta downloads", "use_computer"), ("quanto está o dólar hoje?", "needs_search"), ("gera uma imagem de um gato astronauta", "generate_image"),
         ("coloca um timer de 5 minutos", "set_timer"), ("como está o clima em São Paulo?", "weather"), ("o que está aberto no meu computador?", "use_computer"),
         ("qual o espaço livre do disco C?", "use_computer"), ("me lembra de ligar para o cliente às 15h", "set_alarm"), ("traduz obrigado para inglês", "reply"),
         ("tem alguma reunião agora?", "outlook"), ("o que tem de novo na conversa do João no whatsapp?", "whatsapp|reply|whatsapp_unread"), ("reinicia o serviço do Veeam", "use_computer"),
         ("como eu reinicio o serviço do Veeam?", "ask_expert"), ("qual o comando para ver as portas abertas?", "ask_expert"), ("lê o PDF C:\\docs\\manual.pdf e resume", "use_computer"),
         ("vê o que está nas duas telas", "look_at_screen"), ("oi, tudo bem?", "reply")]
ok = 0
for q, want in CASES:
    picked.clear(); t0 = time.time()
    out, _ = b.run(q, [], "t")
    dt = time.time() - t0
    got = picked[-1] if picked else ("(atalho) " + out[:30].replace("\n", " "))
    good = any(got.startswith(w) or w in got for w in want.split("|")) or (not picked and want == "whatsapp_unread" and "WhatsApp" in out)
    ok += good
    print(f"{'OK  ' if good else 'FAIL'} {dt:5.1f}s  {q[:52]:52s} -> {got}  (esperado {want})", flush=True)
print(f"{ok}/{len(CASES)}")
