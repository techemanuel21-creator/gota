"""The on-device Gemma model through LiteRT-LM (the same engine and model file as the phone app)."""
import json, re, threading, urllib.request
from pathlib import Path
import litert_lm as L
from .store import MODELS, ROOT

MODEL_URL = "https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm/resolve/main/gemma-4-E2B-it.litertlm"
MODEL_FILE = MODELS / "gemma4_e2b.litertlm"
MODEL_MB = 2468
SAMPLER = dict(top_k=40, top_p=0.95, temperature=0.1)  # near zero: the most probable answer, no guessing
MAX_REPLAY = 10
MAX_LIVE_CHARS = 18000
MAX_CONVS = 3   # live conversations kept at once (a chat, the voice chat, a call...): switching between them costs nothing
WARM_PING = '[preparação] Responda apenas {"action":"reply","text":"ok"}'
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
        cache = MODELS / "cache"   # the compiled-model cache lives with the model: built once, shared, never copied per run
        try:
            cache.mkdir(parents=True, exist_ok=True)
        except OSError:            # read-only program folder: fall back to the user's data folder
            cache = ROOT / "cache"
            cache.mkdir(parents=True, exist_ok=True)
        self.engine = L.Engine(str(model_path), backend=L.Backend.CPU(), max_num_tokens=8192,
                               vision_backend=L.Backend.CPU(), max_num_images=1, cache_dir=str(cache))
        self.lock = threading.Lock()
        self.convs = {}      # wanted-key -> [conversation, chars]; oldest is evicted past MAX_CONVS
        self.active = None   # the conversation that is generating right now (so it can be interrupted)
        self.active_key = None
        self.dirty = set()   # conversations whose generation was interrupted: rebuilt from the history on next use
        self.warm_seq = 0

    def _new(self, system, messages=None, think=False):
        return self.engine.create_conversation(
            system_message=system, messages=messages or None,
            sampler_config=L.SamplerConfig(**SAMPLER), thinking_config=L.ThinkingConfig(enable_thinking=think))

    def _drop(self, wanted):
        ent = self.convs.pop(wanted, None)
        if ent is not None:
            try:
                ent[0].__exit__(None, None, None)
            except Exception:
                pass

    def _close(self):
        for wanted in list(self.convs):
            self._drop(wanted)
        self.dirty.clear()

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

    def _ensure(self, key, system, history, think):
        """The live conversation for this chat (built from the instructions and the history if it is not alive). Call with the lock held."""
        wanted = f"{key}|{hash(system)}|{think}"
        if wanted in self.dirty:   # an interrupted generation leaves the conversation in an unknown state
            self._drop(wanted)
            self.dirty.discard(wanted)
        ent = self.convs.get(wanted)
        if ent is not None and ent[1] > MAX_LIVE_CHARS:
            self._drop(wanted)
            ent = None
        fresh = ent is None
        if ent is None:
            while len(self.convs) >= MAX_CONVS:
                self._drop(next(iter(self.convs)))
            turns, older = history[-MAX_REPLAY:], history[:-MAX_REPLAY]
            full = system + ("\n\n" + self._digest(older) if older else "")
            conv = self._new(full, [{"role": r, "content": t} for r, t in turns], think).__enter__()
            ent = self.convs[wanted] = [conv, len(full) + sum(len(t) for _, t in turns)]
        else:
            self.convs[wanted] = self.convs.pop(wanted)   # most recently used goes last
        return wanted, ent, fresh

    def chat(self, key, system, history, user_text, image=None, think=False, on_delta=None):
        """history: [(role 'user'|'model', text)]. One live conversation per chat keeps the cache warm."""
        self.warm_seq += 1   # a real message beats any queued warm-up
        with self.lock:
            wanted, ent, _ = self._ensure(key, system, history, think)
            self.active, self.active_key = ent[0], wanted
            try:
                reply = self._send(ent[0], self._message(user_text, image), on_delta)
            finally:
                self.active = None
            ent[1] += len(user_text) + len(reply)
            return reply

    def warm(self, key, system, history):
        """Reads the instructions and the chat so far into a live conversation in the background, so the first real message does not wait for it."""
        self.warm_seq += 1
        mine = self.warm_seq

        def work():
            with self.lock:
                if mine != self.warm_seq:   # something newer was asked meanwhile
                    return
                try:
                    wanted, ent, fresh = self._ensure(key, system, history, False)
                    if not fresh:   # already alive and read: nothing to do
                        return
                    self.active, self.active_key = ent[0], wanted
                    try:
                        _text(ent[0].send_message(WARM_PING))
                    finally:
                        self.active = None
                    ent[1] += len(WARM_PING) + 40
                except Exception:
                    pass
        threading.Thread(target=work, daemon=True).start()

    def complete(self, messages, on_delta=None):
        """A stateless chat for outside clients (the code editor): messages is the OpenAI-style list [{role: system|user|assistant, content}], the last one from the user."""
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        turns = [{"role": "user" if m["role"] == "user" else "model", "content": m["content"]} for m in messages if m["role"] in ("user", "assistant")]
        last = turns.pop()["content"]
        with self.lock:
            with self._new(system, turns) as conv:
                self.active = conv
                try:
                    return self._send(conv, last, on_delta)
                finally:
                    self.active = None

    def one_shot(self, system, user_text, image=None, on_delta=None):
        with self.lock:
            for attempt in (0, 1):
                try:   # a second, short-lived conversation next to the live chat: the chat keeps its cache and is not rebuilt afterwards
                    with self._new(system) as conv:
                        self.active = conv
                        try:
                            return self._send(conv, self._message(user_text, image), on_delta)
                        finally:
                            self.active = None
                except Exception:
                    if attempt:
                        raise
                    self._close()   # the engine did not accept two at once: free the chat's session and try again

    @staticmethod
    def _send(conv, message, on_delta=None):
        """Sends a message; with on_delta the answer is read as it is generated and on_delta(text_so_far) is called for every piece."""
        if on_delta is None:
            return _text(conv.send_message(message))
        acc = ""
        for chunk in conv.send_message_async(message):
            acc += _text(chunk)
            try:
                on_delta(acc)
            except Exception:
                pass
        return acc

    @staticmethod
    def _message(text, image):
        if not image:
            return text
        return {"role": "user", "content": [{"type": "image", "path": image}, {"type": "text", "text": text}]}

    def cancel(self):
        """Interrupts the answer being generated (if any). Safe to call from any thread."""
        conv = self.active
        if conv is not None:
            if self.active_key:
                self.dirty.add(self.active_key)
            try:
                conv.cancel_process()
            except Exception:
                pass

    def close(self):
        self._close()
