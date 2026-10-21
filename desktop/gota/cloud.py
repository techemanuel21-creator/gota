"""The cloud model (OpenRouter) Gota uses while the computer is online. Offline, or when the cloud does not answer, the on-device Gemma takes over.
The API key is asked on first use and kept encrypted for this Windows user (never in the program or in git)."""
import base64, io, json, os, re, threading, time, urllib.error, urllib.request
from pathlib import Path
from .store import ROOT
from .outlook import _crypt

URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "minimax/minimax-m3.1-flash:free"
KEY_FILE = ROOT / "openrouter.key"
TEMPERATURE = 0.1
RETRY_AFTER_FAIL = 45   # seconds the cloud is skipped after an error, so an offline computer does not wait on every message


class CloudError(Exception):
    pass


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
    def __init__(self, key, model=DEFAULT_MODEL):
        self.key, self.model = key, model or DEFAULT_MODEL
        self.cancelled = threading.Event()
        self.response = None

    def cancel(self):
        self.cancelled.set()
        r = self.response
        if r is not None:
            try:
                r.close()
            except Exception:
                pass

    def _post(self, messages, on_delta=None, retries=1):
        """Sends the messages; with on_delta the answer streams and on_delta(text so far) is called for every piece. Raises CloudError on failure."""
        self.cancelled.clear()
        body = json.dumps({"model": self.model, "messages": messages, "stream": on_delta is not None, "temperature": TEMPERATURE}).encode("utf-8")
        headers = {"Authorization": "Bearer " + self.key, "Content-Type": "application/json", "HTTP-Referer": "https://github.com/techemanuel21-creator/gota", "X-Title": "Gota"}
        for attempt in range(retries + 1):
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
        msgs += [{"role": "user" if r == "user" else "assistant", "content": t} for r, t in history[-20:]]
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
        key = load_key()
        if not key:
            return None
        model = self.settings.get("cloud_model") or DEFAULT_MODEL
        if self._cloud is None or self._cloud.key != key or self._cloud.model != model:
            self._cloud = OpenRouter(key, model)
        return self._cloud

    def cloud_ready(self):
        """True when the next request will go to the cloud model (key set, switched on, and it did not fail a moment ago)."""
        return self._client() is not None

    def _try(self, call, local_call):
        c = self._client()
        if c is not None:
            try:
                out = call(c)
                self.using, self.last_error = "cloud", ""
                return out
            except CloudError as e:
                self.last_error = str(e)
                self.down_until = time.time() + RETRY_AFTER_FAIL
        self.using = "local"
        return local_call()

    def chat(self, key, system, history, user_text, image=None, think=False, on_delta=None):
        return self._try(lambda c: c.chat(key, system, history, user_text, image, think, on_delta),
                         lambda: self.local.chat(key, system, history, user_text, image, think, on_delta))

    def one_shot(self, system, user_text, image=None, on_delta=None):
        return self._try(lambda c: c.one_shot(system, user_text, image, on_delta), lambda: self.local.one_shot(system, user_text, image, on_delta))

    def complete(self, messages, on_delta=None):
        return self._try(lambda c: c.complete(messages, on_delta), lambda: self.local.complete(messages, on_delta))

    def warm(self, key, system, history):
        if self._client() is None:   # the cloud needs no warm-up; the local model does when it is the one answering
            self.local.warm(key, system, history)

    def cancel(self):
        if self._cloud is not None:
            self._cloud.cancel()
        self.local.cancel()
