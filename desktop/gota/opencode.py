"""opencode as the cloud engine of Gota Desktop 2: a local `opencode serve` (127.0.0.1, random password, started on first use, stopped with Gota) answers through the
free models opencode offers (no account and no API key). Gota keeps its own prompts and router; opencode is only the model provider, used as it is meant to be used:
its default tools and permissions are left alone (disabling them makes the free tier refuse the request), the read-only "plan" agent is chosen so the model cannot
edit files, and the session runs in an empty folder of its own."""
import atexit, base64, glob, json, os, secrets, shutil, socket, subprocess, sys, threading, time, urllib.error, urllib.request
from pathlib import Path
from .cloud import OpenRouter, CloudError, clean, HISTORY_MESSAGES, HISTORY_CHARS
from .store import ROOT

DEFAULT_MODEL = "opencode/deepseek-v4.1-flash-free"   # measured 1.8 s for a short answer through the server
FALLBACKS = ["opencode/glm-5.3-flash-free", "opencode/nemotron-3.5-lightning-free", "opencode/big-pickle"]   # the spare of the race when the chosen one stalls
AGENT = "plan"
WORKDIR = ROOT / "opencode"


def find_exe():
    """The opencode.exe that ships inside the project (opencode/ next to the source, or inside the packaged Gota); installs elsewhere are only a fallback."""
    here = [Path(__file__).resolve().parent.parent / "opencode" / "opencode.exe"]
    if getattr(sys, "frozen", False):
        here.insert(0, Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "opencode" / "opencode.exe")
    for cand in here:
        if cand.exists():
            return str(cand)
    for cand in here:   # the repository carries opencode.zip (the exe is 172 MB, over GitHub's file limit): unpack it once, locally, no download
        zipped = cand.with_name("opencode.zip")
        if zipped.exists():
            try:
                import zipfile
                with zipfile.ZipFile(zipped) as z:
                    z.extract("opencode.exe", cand.parent)
                return str(cand)
            except Exception:
                pass
    exe = shutil.which("opencode")
    if exe:
        return exe
    base = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet")
    for pattern in (base + r"\Packages\SST.opencode*\opencode.exe", base + r"\Links\opencode.exe"):
        found = glob.glob(pattern)
        if found:
            return found[0]
    return None


def available():
    return find_exe() is not None


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    """One opencode server per Gota run, shared by every request."""
    _lock = threading.Lock()
    proc = None
    base = ""
    auth = ""

    @classmethod
    def ensure(cls):
        with cls._lock:
            if cls.proc is not None and cls.proc.poll() is None:
                return cls.base, cls.auth
            exe = find_exe()
            if not exe:
                raise CloudError("opencode não está instalado (winget install SST.opencode)")
            WORKDIR.mkdir(parents=True, exist_ok=True)
            port, password = _free_port(), secrets.token_urlsafe(24)
            env = dict(os.environ, OPENCODE_SERVER_PASSWORD=password)
            cls.proc = subprocess.Popen([exe, "serve", "--port", str(port), "--hostname", "127.0.0.1"], cwd=str(WORKDIR), env=env, stdin=subprocess.DEVNULL,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            cls.base = f"http://127.0.0.1:{port}"
            cls.auth = "Basic " + base64.b64encode(f"opencode:{password}".encode()).decode()
            atexit.register(cls.stop)
            deadline = time.time() + 25
            while time.time() < deadline:
                if cls.proc.poll() is not None:
                    break
                try:
                    req = urllib.request.Request(cls.base + "/global/health", headers={"Authorization": cls.auth})
                    with urllib.request.urlopen(req, timeout=2):
                        return cls.base, cls.auth
                except Exception:
                    time.sleep(0.3)
            cls.stop()
            raise CloudError("o servidor do opencode não iniciou")

    @classmethod
    def stop(cls):
        p, cls.proc = cls.proc, None
        if p is not None and p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass


def _call(path, body=None, method=None, timeout=150):
    base, auth = Server.ensure()
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(base + path, data=data, method=method or ("POST" if body is not None else "GET"),
                                 headers={"Authorization": auth, "Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout)


def _transcript(turns):
    return "\n".join(("Usuário: " if r == "user" else "Gota: ") + t for r, t in turns)


class OpenCode(OpenRouter):
    """Same calls as the OpenRouter client (chat, one_shot, complete, cancel, check), answered by opencode's free models."""
    fallbacks = FALLBACKS

    def __init__(self, model=DEFAULT_MODEL, effort=""):
        super().__init__("opencode", model or DEFAULT_MODEL, effort)
        self.session = None

    def sibling(self, model):
        return OpenCode(model, self.effort)

    def sees_images(self):
        return False   # the free vision models are far slower than reading the picture's text; the caller sends the OCR text instead

    def cancel(self):
        self.cancelled.set()
        sid, r = self.session, self.response
        if sid:
            threading.Thread(target=lambda: self._quiet(lambda: _call(f"/session/{sid}/abort", {}, timeout=5).close()), daemon=True).start()
        if r is not None:
            self._quiet(r.close)

    @staticmethod
    def _quiet(fn):
        try:
            fn()
        except Exception:
            pass

    def _post(self, messages, on_delta=None, retries=1):
        return self._post_one(messages, on_delta, retries)

    def _post_one(self, messages, on_delta=None, retries=1):
        self.cancelled.clear()
        system = "\n\n".join(m["content"] for m in messages if m.get("role") == "system" and isinstance(m.get("content"), str))
        turns = []
        for m in messages:
            if m.get("role") not in ("user", "assistant"):
                continue
            c = m["content"]
            if isinstance(c, list):
                c = "\n".join(p.get("text", "") for p in c if p.get("type") == "text")
            turns.append((m["role"], c))
        if not turns:
            raise CloudError("nada para enviar")
        *before, (_, last) = turns
        text = last if not before else "Conversa até aqui:\n" + _transcript(before) + "\n\nMensagem atual do usuário:\n" + last
        provider, _, model = self.model.partition("/")
        body = {"model": {"providerID": provider, "modelID": model}, "agent": AGENT, "parts": [{"type": "text", "text": text}]}
        if system:
            body["system"] = system
        try:
            with _call("/session", {}, timeout=20) as r:
                self.session = json.loads(r.read().decode("utf-8"))["id"]
            sid = self.session
            self.response = _call(f"/session/{sid}/message", body)
            out = json.loads(self.response.read().decode("utf-8"))
        except CloudError:
            raise
        except urllib.error.HTTPError as e:
            raise CloudError(f"opencode {e.code}: {e.read().decode('utf-8', 'ignore')[:160]}")
        except Exception as e:
            if self.cancelled.is_set():
                return ""
            raise CloudError(f"sem resposta do opencode: {e}")
        finally:
            r, sid, self.response, self.session = self.response, self.session, None, None
            if r is not None:
                self._quiet(r.close)
            if sid:
                threading.Thread(target=lambda: self._quiet(lambda: _call(f"/session/{sid}", method="DELETE", timeout=5).close()), daemon=True).start()
        err = (out.get("info") or {}).get("error")
        if err:
            raise CloudError("opencode: " + str((err.get("data") or {}).get("message") or err.get("name"))[:200])
        answer = clean("".join(p.get("text", "") for p in out.get("parts", []) if p.get("type") == "text"))
        if not answer and not self.cancelled.is_set():
            raise CloudError("resposta vazia")
        if on_delta is not None and answer:
            try:
                on_delta(answer)
            except Exception:
                pass
        return answer
