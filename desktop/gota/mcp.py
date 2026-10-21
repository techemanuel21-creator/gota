"""A small MCP client (Model Context Protocol, stdio): plug in any third-party tool server (Slack, databases, calendars, CRMs...) without writing code
for each one. The servers are listed in Settings ("mcp_servers": name, command, args, env); the agent sees them through the `mcp` tool.
Everything a server returns is treated as data, never as instructions, and calls that may change things ask the user first."""
import json, os, subprocess, threading, time

PROTOCOL = "2024-11-05"
NOFLASH = 0x08000000


class McpError(Exception):
    pass


class McpClient:
    def __init__(self, name, command, args=(), env=None, cwd=None):
        self.name, self.command, self.args, self.env, self.cwd = name, command, list(args), env or {}, cwd
        self.proc = None
        self._id = 0
        self._pending = {}
        self._lock = threading.Lock()
        self.tools = []

    # ---- process and JSON-RPC lines
    def start(self, timeout=20):
        if self.proc is not None and self.proc.poll() is None:
            return
        self.proc = subprocess.Popen([self.command, *self.args], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     env={**os.environ, **self.env}, cwd=self.cwd, creationflags=NOFLASH, text=True, encoding="utf-8", bufsize=1)
        threading.Thread(target=self._read, daemon=True).start()
        self.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": {"name": "gota", "version": "1.0"}}, timeout)
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.tools = (self.request("tools/list", {}, timeout) or {}).get("tools", [])

    def _send(self, obj):
        with self._lock:
            self.proc.stdin.write(json.dumps(obj) + "\n")
            self.proc.stdin.flush()

    def _read(self):
        for line in self.proc.stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            slot = self._pending.get(msg.get("id"))
            if slot is not None:
                slot["msg"] = msg
                slot["event"].set()

    def request(self, method, params, timeout=60):
        self._id += 1
        rid = self._id
        slot = self._pending[rid] = {"event": threading.Event(), "msg": None}
        try:
            self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
            if not slot["event"].wait(timeout):
                raise McpError(f"o servidor {self.name} não respondeu a {method}")
        finally:
            self._pending.pop(rid, None)
        msg = slot["msg"]
        if "error" in msg:
            raise McpError(str(msg["error"].get("message", msg["error"]))[:300])
        return msg.get("result")

    def call(self, tool, arguments, timeout=120):
        result = self.request("tools/call", {"name": tool, "arguments": arguments or {}}, timeout) or {}
        text = "\n".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
        return ("ERRO do servidor: " if result.get("isError") else "") + (text or json.dumps(result, ensure_ascii=False)[:1500])

    def read_only(self, tool):
        info = next((t for t in self.tools if t.get("name") == tool), {})
        return bool((info.get("annotations") or {}).get("readOnlyHint"))

    def stop(self):
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
        except Exception:
            pass


class McpHub:
    """The configured servers, started on first use."""

    def __init__(self, settings):
        self.settings = settings
        self.clients = {}

    def configs(self):
        return {c["name"]: c for c in (self.settings.get("mcp_servers") or []) if c.get("name") and c.get("command")}

    def client(self, name):
        cfg = self.configs().get(name)
        if cfg is None:
            raise McpError(f"servidor MCP '{name}' não está configurado (veja Integrações)")
        cli = self.clients.get(name)
        if cli is None or cli.proc is None or cli.proc.poll() is not None:
            cli = self.clients[name] = McpClient(name, cfg["command"], cfg.get("args", []), cfg.get("env"), cfg.get("cwd"))
            cli.start()
        return cli

    def stop(self):
        for c in self.clients.values():
            c.stop()
