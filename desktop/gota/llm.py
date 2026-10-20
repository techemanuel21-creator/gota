"""The on-device Gemma model through LiteRT-LM (the same engine and model file as the phone app)."""
import json, re, threading, urllib.request
from pathlib import Path
import litert_lm as L
from .store import ROOT

MODEL_URL = "https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm/resolve/main/gemma-4-E2B-it.litertlm"
MODEL_FILE = ROOT / "models" / "gemma4_e2b.litertlm"
MODEL_MB = 2468
SAMPLER = dict(top_k=40, top_p=0.95, temperature=0.1)  # near zero: the most probable answer, no guessing
MAX_REPLAY = 8
MAX_LIVE_CHARS = 9000
DIGEST_CHARS = 1500


def download_model(dest: Path, progress):
    """Resumable download; progress(percent, done_mb, total_mb)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0
    headers = {"User-Agent": "GotaDesktop/1.0"}
    if have:
        headers["Range"] = f"bytes={have}-"
    with urllib.request.urlopen(urllib.request.Request(MODEL_URL, headers=headers), timeout=30) as r:
        resumed = r.status == 206
        done = have if resumed else 0
        total = done + int(r.headers.get("Content-Length", 0))
        with open(part, "ab" if resumed else "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total:
                    progress(int(done * 100 / total), done >> 20, total >> 20)
    part.replace(dest)


def _text(message) -> str:
    return "".join(getattr(c, "text", "") for c in message.contents)


class Gemma:
    def __init__(self, model_path):
        (ROOT / "cache").mkdir(parents=True, exist_ok=True)
        self.engine = L.Engine(str(model_path), backend=L.Backend.CPU(), max_num_tokens=4096,
                               vision_backend=L.Backend.CPU(), max_num_images=1, cache_dir=str(ROOT / "cache"))
        self.lock = threading.Lock()
        self.live = None
        self.key = None
        self.chars = 0

    def _new(self, system, messages=None, think=False):
        return self.engine.create_conversation(
            system_message=system, messages=messages or None,
            sampler_config=L.SamplerConfig(**SAMPLER), thinking_config=L.ThinkingConfig(enable_thinking=think))

    def _close(self):
        if self.live is not None:
            try:
                self.live.__exit__(None, None, None)
            except Exception:
                pass
        self.live, self.key, self.chars = None, None, 0

    @staticmethod
    def _digest(older):
        lines = []
        for role, text in older:
            if role == "model":
                try:
                    text = json.loads(text).get("text") or text
                except Exception:
                    pass
            lines.append(("Dono: " if role == "user" else "Você: ") + re.sub(r"\s+", " ", text)[:160])
        head = lines[:2]
        budget = DIGEST_CHARS - sum(len(x) for x in head)
        tail = []
        for line in reversed(lines[2:]):
            if len(line) > budget:
                break
            tail.insert(0, line)
            budget -= len(line)
        mid = ["[...]"] if len(lines) > len(head) + len(tail) else []
        return "Antes, nesta mesma conversa, já foi dito (lembre-se disso):\n" + "\n".join(head + mid + tail)

    def chat(self, key, system, history, user_text, image=None, think=False):
        """history: [(role 'user'|'model', text)]. One live conversation per chat keeps the cache warm."""
        with self.lock:
            wanted = f"{key}|{hash(system)}|{think}"
            if self.live is None or self.key != wanted or self.chars > MAX_LIVE_CHARS:
                self._close()
                turns, older = history[-MAX_REPLAY:], history[:-MAX_REPLAY]
                full = system + ("\n\n" + self._digest(older) if older else "")
                conv = self._new(full, [{"role": r, "content": t} for r, t in turns], think)
                self.live = conv.__enter__()
                self.key = wanted
                self.chars = len(full) + sum(len(t) for _, t in turns)
            reply = _text(self.live.send_message(self._message(user_text, image)))
            self.chars += len(user_text) + len(reply)
            return reply

    def one_shot(self, system, user_text):
        with self.lock:
            self._close()
            with self._new(system) as conv:
                return _text(conv.send_message(user_text))

    @staticmethod
    def _message(text, image):
        if not image:
            return text
        return {"role": "user", "content": [{"type": "image", "path": image}, {"type": "text", "text": text}]}

    def close(self):
        self._close()
