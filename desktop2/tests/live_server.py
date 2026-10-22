"""The editor-facing server with the real model: asks it to fix a buggy function exactly like the VS Code extension does. Needs the model files."""
import json, os, sys, tempfile, time, urllib.request
os.environ["GOTA_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from gota import llm, server

g = llm.Gemma(llm.MODEL_FILE)
srv = server.LocalServer(lambda: g, port=11700)
port = srv.start()
cfg = server.read_config()
SYSTEM = ("Você é um programador sênior. Responda em português do Brasil. Quando devolver código, devolva SOMENTE o código final dentro de UM bloco ``` com a linguagem, "
          "sem explicações antes ou depois, preservando o estilo e a indentação do código original.")
CODE = "def media(numeros):\n    total = 0\n    for n in numeros:\n        total += n\n    return total / len(numeros)\n"
body = {"model": "gota", "stream": True, "messages": [
    {"role": "system", "content": SYSTEM},
    {"role": "user", "content": f"Corrija os erros e melhore este código: tratar lista vazia.\nLinguagem: python. Arquivo: media.py.\n\n```python\n{CODE}```"}]}
req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", data=json.dumps(body).encode(), headers={"Authorization": "Bearer " + cfg["token"], "Content-Type": "application/json"})
t = time.time(); first = None; text = ""
with urllib.request.urlopen(req, timeout=300) as r:
    for raw in r:
        line = raw.decode("utf-8").strip()
        if line.startswith("data: {"):
            piece = json.loads(line[6:])["choices"][0]["delta"].get("content", "")
            if piece and first is None:
                first = time.time() - t
            text += piece
print(f"primeiro pedaço em {first:.1f}s | total {time.time() - t:.1f}s")
print("RESPOSTA:\n" + text)
srv.stop()
