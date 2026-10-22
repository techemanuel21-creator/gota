"""A small local server that lets code editors (the Gota extension for VS Code, or any tool that speaks the OpenAI chat format) use Gota's own model.

Safety: it listens ONLY on this computer (127.0.0.1), every request needs the secret token that Gota writes to %APPDATA%/Gota/vscode.json,
and requests that come from a web page (they carry an Origin header) are refused, so no website can talk to it."""
import json, secrets, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .store import ROOT

CONFIG = ROOT / "vscode.json"
DEFAULT_PORT = 11435
MAX_CHARS = 14000   # about 4,000 tokens: the model's window is 8,192 and needs room to answer


def read_config():
    try:
        return json.loads(CONFIG.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _shorten(messages):
    """Keeps the system message and the most recent turns within MAX_CHARS (long files would not fit in the model's window)."""
    system = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    budget = MAX_CHARS - sum(len(str(m.get("content", ""))) for m in system)
    kept = []
    for m in reversed(rest):
        text = str(m.get("content", ""))
        if len(text) > budget and not kept:      # the last message alone is too long: keep its tail
            text = "[...]\n" + text[-max(budget, 2000):]
        if budget <= 0:
            break
        kept.append({"role": m.get("role"), "content": text})
        budget -= len(text)
    return system + list(reversed(kept))


class LocalServer:
    def __init__(self, llm_getter, port=DEFAULT_PORT):
        self.llm, self.port = llm_getter, port
        self.httpd = None
        self.token = ""

    @property
    def running(self):
        return self.httpd is not None

    def start(self):
        """Starts listening (if not already) and writes the connection file the editor extension reads. Returns the port."""
        if self.httpd is not None:
            return self.port
        cfg = read_config()
        self.token = cfg.get("token") or secrets.token_urlsafe(24)
        server = self
        gemma = self.llm

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype="application/json"):
                data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", ctype + "; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _allowed(self):
                if self.headers.get("Origin"):   # a web page is calling: never
                    self._send(403, {"error": {"message": "forbidden"}})
                    return False
                if self.headers.get("Authorization", "") != f"Bearer {server.token}":
                    self._send(401, {"error": {"message": "invalid token"}})
                    return False
                return True

            def do_GET(self):
                if not self._allowed():
                    return
                path = self.path.split("?")[0]
                if path == "/health":
                    self._send(200, {"ok": True, "model_ready": gemma() is not None})
                elif path in ("/v1/models", "/models"):
                    self._send(200, {"object": "list", "data": [{"id": "gota", "object": "model", "owned_by": "local"}]})
                else:
                    self._send(404, {"error": {"message": "not found"}})

            def do_POST(self):
                if not self._allowed():
                    return
                if self.path.split("?")[0] not in ("/v1/chat/completions", "/chat/completions"):
                    return self._send(404, {"error": {"message": "not found"}})
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                    req = json.loads(self.rfile.read(length) or b"{}")
                    messages = [m for m in req.get("messages", []) if m.get("role") in ("system", "user", "assistant")]
                    for m in messages:   # content may be a list of parts (OpenAI format)
                        if isinstance(m.get("content"), list):
                            m["content"] = "".join(p.get("text", "") for p in m["content"] if isinstance(p, dict))
                    if not messages or messages[-1]["role"] != "user":
                        return self._send(400, {"error": {"message": "the last message must be from the user"}})
                except (ValueError, KeyError):
                    return self._send(400, {"error": {"message": "bad request"}})
                model = gemma()
                if model is None:
                    return self._send(503, {"error": {"message": "Gota is still loading its model"}})
                messages = _shorten(messages)
                stamp, cid = int(time.time()), "chatcmpl-" + secrets.token_hex(6)
                if req.get("stream"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    sent = {"n": 0}

                    def chunk(delta, finish=None):
                        body = {"id": cid, "object": "chat.completion.chunk", "created": stamp, "model": "gota", "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
                        self.wfile.write(b"data: " + json.dumps(body, ensure_ascii=False).encode("utf-8") + b"\n\n")
                        self.wfile.flush()

                    def on_delta(acc):
                        if len(acc) > sent["n"]:
                            chunk({"content": acc[sent["n"]:]})
                            sent["n"] = len(acc)
                    try:
                        chunk({"role": "assistant"})
                        model.complete(messages, on_delta)
                        chunk({}, "stop")
                        self.wfile.write(b"data: [DONE]\n\n")
                        self.wfile.flush()
                    except (OSError, ValueError):
                        pass
                    self.close_connection = True
                    return
                try:
                    text = model.complete(messages)
                except Exception as e:
                    return self._send(500, {"error": {"message": str(e)[:200]}})
                self._send(200, {"id": cid, "object": "chat.completion", "created": stamp, "model": "gota",
                                 "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                                 "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}})

        for port in range(self.port, self.port + 20):   # the next free one if this is taken
            try:
                self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
                self.port = port
                break
            except OSError:
                continue
        if self.httpd is None:
            raise OSError("não achei uma porta livre")
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        ROOT.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps({"port": self.port, "token": self.token, "url": f"http://127.0.0.1:{self.port}/v1"}), "utf-8")
        return self.port

    def stop(self):
        if self.httpd is not None:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass
        self.httpd = None
        try:
            CONFIG.unlink()   # the extension then shows "Gota is off"
        except OSError:
            pass
