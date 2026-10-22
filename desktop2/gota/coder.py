"""Coding mode: a project chat is carried out by opencode's "build" agent (it edits files and runs commands in the project folder; LSP diagnostics and code formatters run
inside opencode), shown with Gota's own look. Gota only translates: what the agent does becomes the steps card, its text the answer, and its permission requests the
confirmation dialog. Gota's safety stays on top: dangerous commands are denied, unknown commands ask first (see PERMISSIONS)."""
import json, os, queue, subprocess, threading, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
from . import opencode as oc
from .cloud import CloudError

# last matching rule wins: everything asks, the usual development commands are allowed, the destructive ones are denied
SAFE_COMMANDS = ["python *", "py *", "pytest *", "pip list*", "pip show*", "pip install -r*", "git status*", "git diff*", "git log*", "git add*", "git commit*", "git branch*", "git checkout*",
                 "git stash*", "npm test*", "npm run *", "npm install*", "npx *", "node *", "tsc*", "yarn *", "pnpm *", "go test*", "go build*", "go run*", "cargo test*", "cargo build*",
                 "cargo run*", "dotnet build*", "dotnet test*", "dotnet run*", "mvn test*", "mvn package*", "gradle *", "dir*", "ls*", "cat *", "type *", "echo *", "findstr *", "where *",
                 "mkdir *", "cd *", "pwd*", "tree*", "php *", "ruby *", "java *", "javac *", "make*", "cmake*", "uv *", "ruff *", "black *", "eslint*", "prettier*"]
DENIED_COMMANDS = ["rm -rf*", "rm -r *", "rmdir /s*", "rd /s*", "del /s*", "del /f*", "Remove-Item *-Recurse*", "format *", "shutdown*", "git push --force*", "git push -f*", "git reset --hard*",
                   "git clean*", "reg delete*", "diskpart*", "cipher /w*", "curl *| *sh*", "iwr *| *iex*", "Invoke-Expression*"]
PERMISSIONS = {"bash": dict([("*", "ask")] + [(p, "allow") for p in SAFE_COMMANDS] + [(p, "deny") for p in DENIED_COMMANDS]),
               "edit": "allow", "external_directory": "ask", "webfetch": "allow"}
CONFIG = {"permission": PERMISSIONS}

PLAIN = {"read": "path", "write": "filePath", "edit": "filePath", "bash": "command", "glob": "pattern", "grep": "pattern", "webfetch": "url", "list": "path", "patch": "filePath"}
SKIP_STEPS = ("todowrite", "todoread")


def describe(tool, state, project):
    inp = (state or {}).get("input") or {}
    key = PLAIN.get(tool)
    what = str(inp.get(key) or inp.get("filePath") or inp.get("path") or inp.get("pattern") or inp.get("description") or "")
    if key in ("path", "filePath") and what:
        try:
            what = str(Path(what).resolve().relative_to(Path(project).resolve()))
        except Exception:
            pass
    return f"{tool} {what[:160]}".strip()


class Coder:
    def __init__(self, project, model=None, session=None):
        self.project, self.session = str(project), session
        self.model = model or oc.DEFAULT_MODEL
        self.current = None   # the running request, for cancel()

    # ------------------------------------------------------------------ plumbing
    def _url(self, path):
        base, auth = oc.Server.ensure()
        return base + path + ("&" if "?" in path else "?") + "directory=" + urllib.parse.quote(self.project), auth

    def _req(self, path, body=None, method=None, timeout=60):
        url, auth = self._url(path)
        req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode("utf-8"), method=method or ("POST" if body is not None else "GET"),
                                     headers={"Authorization": auth, "Content-Type": "application/json"})
        return urllib.request.urlopen(req, timeout=timeout)

    def _json(self, path, body=None, method=None, timeout=60):
        try:
            with self._req(path, body, method, timeout) as r:
                raw = r.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            raise CloudError(f"opencode {e.code}: {e.read().decode('utf-8', 'ignore')[:160]}")
        except Exception as e:
            raise CloudError(f"sem resposta do opencode: {e}")
        return json.loads(raw) if raw.strip() else {}

    def ensure_session(self):
        if self.session:
            try:
                self._json(f"/session/{self.session}")
                return self.session
            except CloudError:
                self.session = None
        self.session = self._json("/session", {})["id"]
        return self.session

    # ------------------------------------------------------------------ what opencode offers
    def commands(self):
        return [(c.get("name"), c.get("description") or "") for c in self._json("/command") if c.get("name")]

    def sessions(self):
        rows = self._json("/session")
        return [(s["id"], s.get("title") or "(sem título)", (s.get("time") or {}).get("updated", 0)) for s in rows]

    def changes(self):
        """What changed in the project folder (git status and a size summary); "" when it is not a git repository or nothing changed."""
        out = []
        for args in (["status", "--short"], ["diff", "--stat"]):
            try:
                r = subprocess.run(["git", "-C", self.project] + args, capture_output=True, text=True, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if r.returncode == 0 and r.stdout.strip():
                    out.append(r.stdout.strip())
            except Exception:
                pass
        return "\n\n".join(out)

    def last_message_id(self, role):
        msgs = self._json(f"/session/{self.ensure_session()}/message?limit=30")
        ids = [m["info"]["id"] for m in msgs if m["info"].get("role") == role]
        return ids[-1] if ids else None

    def undo(self):
        mid = self.last_message_id("user")
        if not mid:
            return False
        self._json(f"/session/{self.ensure_session()}/revert", {"messageID": mid})
        return True

    def redo(self):
        self._json(f"/session/{self.ensure_session()}/unrevert", {})

    def compact(self):
        prov, _, model = self.model.partition("/")
        self._json(f"/session/{self.ensure_session()}/summarize", {"providerID": prov, "modelID": model}, timeout=180)

    def open_terminal(self):
        """opencode's own terminal interface, attached to the same server and session (full original experience, in a console window)."""
        base, _ = oc.Server.ensure()
        sid = self.ensure_session()
        bat = oc.WORKDIR / "terminal.bat"   # the server password travels in the environment of the new console, never in a file
        bat.write_text(f'@echo off\ncd /d "{self.project}"\n"{oc.find_exe()}" attach {base} --dir "{self.project}" --session {sid}\n', encoding="utf-8")
        subprocess.Popen(f'cmd /k ""{bat}""', env=dict(os.environ, OPENCODE_SERVER_PASSWORD=oc.Server.password), creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))

    def cancel(self):
        self.current and self.current.set()
        if self.session:
            try:
                self._req(f"/session/{self.session}/abort", {}, timeout=5).close()
            except Exception:
                pass

    # ------------------------------------------------------------------ one request
    def run(self, text, on_text=None, on_step=None, ask=None, timeout=900):
        """Sends `text` (or a "/command") to the build agent and follows it until it is done.
        on_text(answer so far) streams the answer, on_step(line) reports each action, ask(description) -> bool answers a permission request.
        Returns {"text", "steps", "session"}."""
        sid = self.ensure_session()
        stop = self.current = threading.Event()
        events = queue.Queue()
        sse = self._req("/event", timeout=timeout + 30)

        def reader():
            try:
                for raw in sse:
                    line = raw.decode("utf-8", "ignore").strip()
                    if line.startswith("data:"):
                        try:
                            events.put(json.loads(line[5:]))
                        except ValueError:
                            pass
            except Exception:
                pass
            events.put(None)
        threading.Thread(target=reader, daemon=True).start()
        prov, _, model = self.model.partition("/")
        try:
            if text.startswith("/"):
                name, _, args = text[1:].partition(" ")
                self._req(f"/session/{sid}/command", {"command": name, "arguments": args.strip(), "model": self.model}, timeout=30).close()
            else:
                self._req(f"/session/{sid}/prompt_async", {"model": {"providerID": prov, "modelID": model}, "agent": "build", "parts": [{"type": "text", "text": text}]}, timeout=30).close()
        except urllib.error.HTTPError as e:
            sse.close()
            raise CloudError(f"opencode {e.code}: {e.read().decode('utf-8', 'ignore')[:160]}")
        roles, texts, order, tools, steps = {}, {}, [], {}, []
        deadline = time.time() + timeout
        try:
            while not stop.is_set() and time.time() < deadline:
                try:
                    e = events.get(timeout=1)
                except queue.Empty:
                    continue
                if e is None:
                    raise CloudError("a conexão com o opencode caiu")
                kind, p = e.get("type", ""), e.get("properties", {})
                if kind == "message.updated":
                    info = p.get("info", {})
                    if info.get("sessionID") == sid:
                        roles[info["id"]] = info.get("role")
                        if info.get("error"):
                            raise CloudError("opencode: " + str((info["error"].get("data") or {}).get("message") or info["error"].get("name"))[:200])
                elif kind == "message.part.updated":
                    part = p.get("part", {})
                    if part.get("sessionID") != sid:
                        continue
                    if part.get("type") == "text" and roles.get(part.get("messageID")) != "user":
                        if part["id"] not in texts:
                            order.append(part["id"])
                        texts[part["id"]] = part.get("text", "")
                        on_text and on_text("\n\n".join(texts[i] for i in order if texts[i].strip()))
                    elif part.get("type") == "tool" and part.get("tool") not in SKIP_STEPS:
                        status = (part.get("state") or {}).get("status")
                        if status in ("running", "completed", "error") and tools.get(part["id"]) != "done":
                            line = describe(part["tool"], part["state"], self.project)
                            if status != "running":
                                tools[part["id"]] = "done"
                                steps.append(line + (" (erro)" if status == "error" else ""))
                            on_step and on_step(line, status)
                elif kind == "message.part.delta" and p.get("sessionID") == sid and p.get("field") == "text":
                    pid = p.get("partID")
                    if pid in texts:
                        texts[pid] += p.get("delta", "")
                        on_text and on_text("\n\n".join(texts[i] for i in order if texts[i].strip()))
                elif kind in ("permission.asked", "permission.v2.asked") and p.get("sessionID") == sid:
                    what = f"{p.get('permission') or p.get('tool') or 'ação'}: " + ", ".join(map(str, p.get("patterns") or [])) if p.get("patterns") else str(p.get("permission") or "ação")
                    ok = bool(ask and ask(what))
                    path = f"/permission/{p['id']}/reply"
                    self._json(path, {"reply": "once" if ok else "reject"})
                elif kind in ("question.asked", "question.v2.asked") and p.get("sessionID") == sid:
                    try:
                        self._json(f"/question/{p['id']}/reject", {})   # Gota's chat has no multiple-choice prompt: the agent continues with its best guess
                    except CloudError:
                        pass
                elif kind == "session.error" and p.get("sessionID") in (sid, None):
                    err = p.get("error") or {}
                    raise CloudError("opencode: " + str((err.get("data") or {}).get("message") or err.get("name") or "erro")[:200])
                elif kind == "session.idle" and p.get("sessionID") == sid:
                    break
            else:
                if not stop.is_set():
                    raise CloudError("o opencode demorou demais")
        finally:
            sse.close()
            self.current = None
        answer = "\n\n".join(texts[i] for i in order if texts[i].strip()).strip()
        if not answer and not stop.is_set():   # the agent ended with a tool and no words: its last written message, if there is one
            try:
                for m in reversed(self._json(f"/session/{sid}/message?limit=10")):
                    words = "\n".join(pt.get("text", "") for pt in m["parts"] if pt.get("type") == "text").strip()
                    if m["info"].get("role") == "assistant" and words:
                        answer = words
                        break
            except CloudError:
                pass
        return {"text": answer, "steps": steps, "session": sid}
