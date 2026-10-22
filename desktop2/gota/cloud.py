"""The cloud model (OpenRouter) Gota uses while the computer is online. Offline, or when the cloud does not answer, the on-device Gemma takes over.
The API key is asked on first use and kept encrypted for this Windows user (never in the program or in git)."""
import base64, io, json, os, re, threading, time, urllib.error, urllib.request
from pathlib import Path
from .store import ROOT
from .outlook import _crypt

URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"    # text only
VISION_MODELS = ["google/gemma-4-31b-it:free", "nvidia/nemotron-3.5-super-vl:free", "openrouter/free"]   # tried in order when a picture is part of the request
FALLBACK_MODELS = ["nvidia/nemotron-3.5-lightning:free", "thinkingmachines/inkling:free", "openrouter/free"]   # the spare of the race and the choice when the chosen model was retired: measured good first, the random router last
KEY_FILE = ROOT / "openrouter.key"
TEMPERATURE = 0.1
HISTORY_MESSAGES = 1500      # conversation sent to the cloud model: measured 3.9 s to first text with 900 thousand characters of context
HISTORY_CHARS = 600_000
RETRY_AFTER_FAIL = 45   # seconds the cloud is skipped after an error, so an offline computer does not wait on every message


class CloudError(Exception):
    pass


class ModelGone(CloudError):
    """The provider retired the model (e.g. the end of a free period): another one must be used."""


_MODALITIES = {}


def has_vision(model):
    """Whether `model` takes pictures (from OpenRouter's public model list, read once). Unknown models count as text-only."""
    if not _MODALITIES:
        try:
            req = urllib.request.Request("https://openrouter.ai/api/v1/models", headers={"User-Agent": "GotaDesktop/1.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                for m in json.loads(r.read().decode("utf-8", "ignore")).get("data", []):
                    _MODALITIES[m["id"]] = "image" in (m.get("architecture", {}).get("input_modalities") or [])
        except Exception:
            _MODALITIES["__failed__"] = False
    return bool(_MODALITIES.get(model))


# ---------------------------------------------------------------------- the key (DPAPI: opens only for this Windows user)
def load_key():
    env = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if env:
        return env
    try:
        return _crypt(KEY_FILE.read_bytes(), False).decode("utf-8").strip()
    except Exception:
        return ""


def save_key(key):
    key = key.strip()
    if not key:
        clear_key()
        return
    KEY_FILE.write_bytes(_crypt(key.encode("utf-8"), True))


def clear_key():
    try:
        KEY_FILE.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------- helpers
_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)


def clean(text):
    """The answer without the model's private reasoning (<think>...</think>), also while it is still being written."""
    text = _THINK.sub("", text)
    cut = text.lower().find("<think>")
    return (text[:cut] if cut >= 0 else text).lstrip()


def _image_part(path):
    """The picture as an OpenAI-style data URL, shrunk when it is large."""
    from PIL import Image
    im = Image.open(path)
    im.load()
    if max(im.size) > 2400:
        im.thumbnail((2400, 2400))
    buf = io.BytesIO()
    if im.mode in ("RGBA", "LA", "P") and Path(path).suffix.lower() == ".png":
        im.save(buf, "PNG")
        mime = "image/png"
    else:
        im.convert("RGB").save(buf, "JPEG", quality=88)
        mime = "image/jpeg"
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64," + base64.b64encode(buf.getvalue()).decode()}}


def _content(text, image):
    if not image:
        return text
    return [{"type": "text", "text": text}, _image_part(image)]


class OpenRouter:
    def __init__(self, key, model=DEFAULT_MODEL, effort="low"):
        self.key, self.model, self.effort = key, model or DEFAULT_MODEL, effort
        self.cancelled = threading.Event()
        self.response = None

    def cancel(self):
        self.cancelled.set()
        holder = getattr(self, "response_holder", None)
        if holder is not None and holder is not self:
            holder.cancel()
        r = self.response
        if r is not None:
            try:
                r.close()
            except Exception:
                pass

    def _post(self, messages, on_delta=None, retries=1):
        """Sends the messages; with on_delta the answer streams and on_delta(text so far) is called for every piece. Raises CloudError on failure.
        A request that carries a picture goes to a vision model when the chosen one is text-only."""
        has_image = any(isinstance(m.get("content"), list) and any(p.get("type") == "image_url" for p in m["content"]) for m in messages)
        if has_image and not has_vision(self.model):
            last = None
            for vm in VISION_MODELS:
                try:
                    clone = OpenRouter(self.key, vm, self.effort)
                    self.response_holder = clone
                    return clone._post_one(messages, on_delta, 0)
                except CloudError as e:
                    last = e
            raise last or CloudError("nenhum modelo de visão respondeu")
        return self._post_one(messages, on_delta, retries)

    def cancel_all(self):
        pass

    @property
    def fallbacks(self):
        return FALLBACK_MODELS

    def sibling(self, model):
        """The same client for another model (the spare of the race, or the replacement of a retired one)."""
        return OpenRouter(self.key, model, self.effort)

    def sees_images(self):
        return has_vision(self.model)

    def _post_one(self, messages, on_delta=None, retries=1):
        self.cancelled.clear()
        payload = {"model": self.model, "messages": messages, "stream": on_delta is not None, "temperature": TEMPERATURE}
        if self.effort and not getattr(self, "_no_effort", False):
            payload["reasoning"] = {"effort": self.effort}   # "minimal": the model thinks very little before answering (10 s instead of 40-115 s on a long script)
        body = json.dumps(payload).encode("utf-8")
        headers = {"Authorization": "Bearer " + self.key, "Content-Type": "application/json", "HTTP-Referer": "https://github.com/techemanuel21-creator/gota", "X-Title": "Gota"}
        for attempt in range(retries + 2):
            try:
                req = urllib.request.Request(URL, data=body, headers=headers, method="POST")
                self.response = urllib.request.urlopen(req, timeout=60)
                break
            except urllib.error.HTTPError as e:
                detail = ""
                try:
                    detail = json.loads(e.read().decode("utf-8", "ignore")).get("error", {}).get("message", "")
                except Exception:
                    pass
                if e.code == 400 and "reasoning" in payload and "reason" in detail.lower():   # this model does not take the setting: ask again without it, and remember
                    self._no_effort = True
                    payload.pop("reasoning")
                    body = json.dumps(payload).encode("utf-8")
                    continue
                if e.code in (404, 410) and re.search(r"retired|ended|no longer|deprecat|sunset|not available", detail, re.I):
                    raise ModelGone(f"o modelo {self.model} foi aposentado: {detail[:160]}")
                if e.code in (429, 502, 503, 504) and attempt < retries:
                    time.sleep(2)
                    continue
                raise CloudError(f"OpenRouter {e.code}: {detail[:200]}")
            except Exception as e:
                raise CloudError(f"sem acesso ao OpenRouter: {e}")
        acc = ""
        try:
            if on_delta is None:
                data = json.loads(self.response.read().decode("utf-8", "ignore"))
                if data.get("error"):
                    raise CloudError(str(data["error"].get("message", data["error"]))[:200])
                return clean(data["choices"][0]["message"].get("content") or "")
            for raw in self.response:
                if self.cancelled.is_set():
                    break
                line = raw.decode("utf-8", "ignore").strip()
                if not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    obj = json.loads(chunk)
                except ValueError:
                    continue
                if obj.get("error"):
                    raise CloudError(str(obj["error"].get("message", obj["error"]))[:200])
                piece = (obj.get("choices") or [{}])[0].get("delta", {}).get("content") or ""
                if piece:
                    acc += piece
                    try:
                        on_delta(clean(acc))
                    except Exception:
                        pass
        except CloudError:
            raise
        except Exception as e:
            if self.cancelled.is_set():
                return clean(acc)
            raise CloudError(f"a resposta foi interrompida: {e}")
        finally:
            try:
                self.response.close()
            except Exception:
                pass
            self.response = None
        out = clean(acc)
        if not out and not self.cancelled.is_set():
            raise CloudError("resposta vazia")
        return out

    # the same calls the on-device model offers -----------------------------------------------------------------
    def chat(self, key, system, history, user_text, image=None, think=False, on_delta=None):
        msgs = [{"role": "system", "content": system}]
        kept, chars = [], 0
        for r, t in reversed(history[-HISTORY_MESSAGES:]):   # the WHOLE conversation (the cloud model reads 200 thousand tokens in a few seconds), newest first, within a size budget
            chars += len(t)
            if chars > HISTORY_CHARS and kept:
                break
            kept.append({"role": "user" if r == "user" else "assistant", "content": t})
        msgs += kept[::-1]
        msgs.append({"role": "user", "content": _content(user_text, image)})
        return self._post(msgs, on_delta)

    def one_shot(self, system, user_text, image=None, on_delta=None):
        return self._post([{"role": "system", "content": system}, {"role": "user", "content": _content(user_text, image)}], on_delta)

    def complete(self, messages, on_delta=None):
        return self._post([{"role": m["role"], "content": m["content"]} for m in messages if m.get("role") in ("system", "user", "assistant")], on_delta)

    def check(self):
        """Tiny request to see that the key and the model work. Returns None when fine, else the reason."""
        try:
            self._post([{"role": "user", "content": "Responda apenas: ok"}])
            return None
        except CloudError as e:
            return str(e)


class Hybrid:
    """Looks like the on-device model to the rest of the program: online it asks the cloud model, offline (or if the cloud fails) the local one answers."""

    def __init__(self, local, settings):
        self.local, self.settings = local, settings
        self.down_until = 0.0
        self.last_error = ""
        self.using = "local"   # "cloud" or "local": what answered last
        self._cloud = None

    def __getattr__(self, name):   # anything else (close, lock, engine...) is the local model's
        return getattr(self.local, name)

    def _client(self):
        if self.settings.get("use_cloud") is False or time.time() < self.down_until:
            return None
        if self.settings.get("engine") != "openrouter":   # opencode's free models first, when it is installed
            from . import opencode
            if opencode.available():
                model = self.settings.get("oc_model") or opencode.DEFAULT_MODEL
                if model in getattr(self, "retired", ()):
                    model = next((m for m in opencode.FALLBACKS if m not in self.retired), model)
                if not isinstance(self._cloud, opencode.OpenCode) or self._cloud.model != model:
                    self._cloud = opencode.OpenCode(model)
                return self._cloud
        key = load_key()
        if not key:
            return None
        model = self.settings.get("cloud_model") or DEFAULT_MODEL
        if model in getattr(self, "retired", ()):
            model = next((m for m in FALLBACK_MODELS if m not in self.retired), model)
        effort = self.settings.get("cloud_effort") or "low"
        if self._cloud is None or self._cloud.key != key or self._cloud.model != model or self._cloud.effort != effort:
            self._cloud = OpenRouter(key, model, effort)
        return self._cloud

    def text_only(self):
        """True when the next request goes to a cloud model that cannot see pictures: the caller sends the text read from the picture instead (much faster than a vision model)."""
        cl = self._client()
        return cl is not None and not (cl.sees_images() if hasattr(cl, "sees_images") else has_vision(cl.model))

    def cloud_ready(self):
        """True when the next request will go to the cloud model (key set, switched on, and it did not fail a moment ago)."""
        return self._client() is not None

    notice = None   # set when the chosen model was retired: the window shows it once

    HEDGE_SECONDS = 16   # a free model that has not started answering after this long is raced against a second one (the spare repeats the whole prompt: tokens and daily quota)

    def _race(self, call, user_cb):
        """call(client, on_delta) -> text. Runs the chosen model; if it has not produced its first words within HEDGE_SECONDS (free models queue and stall), a second model
        is started too and the first to speak wins; the other is cancelled. Same words on screen either way, and no waiting on the slow one."""
        import queue as _q
        primary = self._client()
        spare = None
        if not hasattr(primary, "model"):
            return call(primary, user_cb)
        if self.settings.get("hedge") is not False:
            spare = next((m for m in getattr(primary, "fallbacks", FALLBACK_MODELS) if m != primary.model and m not in getattr(self, "retired", ())), None)
        if spare is None:
            return call(primary, user_cb)
        lock, state, clients, results = threading.Lock(), {"winner": None}, {}, _q.Queue()
        spoke = threading.Event()

        def gate(idx):
            def cb(text):
                with lock:
                    if state["winner"] is None:
                        state["winner"] = idx
                        spoke.set()
                        other = clients.get(1 - idx)
                        if other is not None:
                            other.cancel()
                    if state["winner"] != idx:
                        return
                if user_cb:
                    user_cb(text)
            return cb

        def worker(idx, client):
            clients[idx] = client
            try:
                results.put((idx, call(client, gate(idx)), None))
            except Exception as e:
                results.put((idx, None, e))
        threading.Thread(target=worker, args=(0, primary), daemon=True).start()
        pending, raced = 1, False
        deadline = time.time() + self.HEDGE_SECONDS
        errors = []

        def start_spare():
            nonlocal pending, raced
            raced = True
            self.last_hedge = spare
            threading.Thread(target=worker, args=(1, primary.sibling(spare) if hasattr(primary, "sibling") else OpenRouter(primary.key, spare, primary.effort)), daemon=True).start()
            pending += 1
        while pending:
            try:
                idx, out, err = results.get(timeout=None if raced else max(0.0, deadline - time.time()))
            except _q.Empty:   # the first model has said nothing for HEDGE_SECONDS: race a second one (unless it has just started to speak)
                if spoke.is_set():
                    raced = True
                else:
                    start_spare()
                continue
            pending -= 1
            if err is None and state["winner"] in (None, idx):
                for k, cl in clients.items():
                    if k != idx:
                        cl.cancel()
                return out
            if err is not None:
                if isinstance(err, ModelGone):
                    raise err   # a retired model is not "slow": switch models for good (the caller handles it)
                errors.append(err)
                if not raced:   # it failed outright: do not wait, go to the second model now
                    start_spare()
        raise errors[0] if errors else CloudError("nenhum modelo respondeu")

    def _try(self, call, local_call, user_cb=None):
        c = self._client()
        if c is not None:
            try:
                try:
                    out = self._race(call, user_cb)
                except ModelGone:
                    self.retired = getattr(self, "retired", set()) | {c.model}
                    fb = next((m for m in getattr(c, "fallbacks", FALLBACK_MODELS) if m not in self.retired and m != c.model), None)
                    if fb is None:
                        raise
                    self.notice = f"O modelo {c.model} foi aposentado pelo provedor. Estou usando {fb}; escolha outro em Nuvem."
                    self._cloud = c.sibling(fb) if hasattr(c, "sibling") else OpenRouter(c.key, fb, c.effort)
                    out = self._race(call, user_cb)
                self.using, self.last_error = "cloud", ""
                from . import tools
                tools.mark_online()
                return out
            except CloudError as e:
                self.last_error = str(e)
                self.down_until = time.time() + RETRY_AFTER_FAIL
        self.using = "local"
        return local_call()

    def chat(self, key, system, history, user_text, image=None, think=False, on_delta=None):
        return self._try(lambda c, cb: c.chat(key, system, history, user_text, image, think, cb),
                         lambda: self.local.chat(key, system, history, user_text, image, think, on_delta), on_delta)

    def one_shot(self, system, user_text, image=None, on_delta=None):
        return self._try(lambda c, cb: c.one_shot(system, user_text, image, cb), lambda: self.local.one_shot(system, user_text, image, on_delta), on_delta)

    def complete(self, messages, on_delta=None):
        return self._try(lambda c, cb: c.complete(messages, cb), lambda: self.local.complete(messages, on_delta), on_delta)

    def warm(self, key, system, history):
        if self._client() is None:   # the cloud needs no warm-up; the local model does when it is the one answering
            self.local.warm(key, system, history)

    def cancel(self):
        if self._cloud is not None:
            self._cloud.cancel()
        self.local.cancel()
