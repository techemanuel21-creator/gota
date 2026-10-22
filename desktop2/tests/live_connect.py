"""WhatsApp and Outlook requests with the real model: refusal when not connected, and the right action + data when connected (sending and Graph are faked)."""
import os, sys, tempfile
os.environ["GOTA_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
from gota import brain, store, llm

p = store.Profile(); p.set_name("emanuel", "senhor"); s = store.Settings()
g = llm.Gemma(os.environ.get("GOTA_MODEL") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "gemma4_e2b.litertlm"))
b = brain.Brain(p, s, lambda: g, images=None)
b.on_phase = lambda x: None
b.hide_window = lambda hide: None
sent = []

def fake_send(contact, message="", image=None, confirm=lambda f: True, on_status=lambda s: None):
    ok = confirm(contact.title())
    sent.append((contact, message, str(image) if image else None, ok))
    return contact.title()
b.whatsapp.send = fake_send
b.confirm = lambda text, danger: (print("   [CONFIRMAÇÃO]", text.replace("\n", " | ")), True)[1]

print("=== SEM CONEXÃO ===")
b.whatsapp.connected = lambda: False
b.outlook.connected = lambda: False
for q in ("tira um print da tela e manda pro João no WhatsApp", "qual é a minha agenda de hoje no Outlook?", "no Outlook, quais e-mails importantes eu tenho que responder ainda?"):
    print(f"> {q}\n  {b.run(q, [], 'a')[0]}", flush=True)

print("\n=== CONECTADO (simulado) ===")
b.whatsapp.connected = lambda: True
b.outlook.connected = lambda: True
b.outlook.agenda = lambda days=1, start=None: [{"title": "Daily de infraestrutura", "start": "2026-10-20 09:00", "end": "2026-10-20 09:15", "where": "Teams", "all_day": False, "online": True, "organizer": "Ana"},
                                              {"title": "Revisão dos backups do Veeam", "start": "2026-10-20 14:30", "end": "2026-10-20 15:30", "where": "Sala 3", "all_day": False, "online": False, "organizer": "Carlos"}]
b.outlook.emails = lambda top=25, unread_only=False, days=14: [
    {"from": "Zabbix <alerta@empresa.com>", "subject": "[PROBLEMA] SRV-DC01 sem resposta", "received": "2026-10-19 22:10", "unread": True, "importance": "high", "flagged": False, "attachments": False, "preview": "Host SRV-DC01 não responde a ping há 10 minutos", "answered": False},
    {"from": "Marina Souza <marina@empresa.com>", "subject": "Prazo do relatório de auditoria", "received": "2026-10-19 16:40", "unread": True, "importance": "high", "flagged": True, "attachments": False, "preview": "Emanuel, você consegue me enviar o relatório até quarta? O auditor está cobrando.", "answered": False},
    {"from": "Newsletter <news@loja.com>", "subject": "Promoções da semana", "received": "2026-10-19 09:00", "unread": False, "importance": "normal", "flagged": False, "attachments": False, "preview": "Aproveite 30% de desconto", "answered": False},
    {"from": "Bruno Lima <bruno@empresa.com>", "subject": "Reunião de quinta", "received": "2026-10-18 11:00", "unread": False, "importance": "normal", "flagged": False, "attachments": False, "preview": "Pode confirmar presença?", "answered": True}]
for q in ("qual é a minha agenda de hoje no Outlook?", "no Outlook, quais e-mails importantes eu tenho que responder ainda?"):
    print(f"> {q}\n  {b.run(q, [], 'b')[0]}", flush=True)
for q in ("tira um print da tela e manda pro João no WhatsApp", "tira um print só da metade direita da tela e manda pra Maria dizendo olha isso", "manda uma mensagem pro Carlos falando que vou atrasar 10 minutos"):
    sent.clear()
    out = b.run(q, [], "c")[0]
    print(f"> {q}\n  {out}\n  envio registrado: {sent}", flush=True)
