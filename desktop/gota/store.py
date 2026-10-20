"""Everything Gota remembers, as small JSON files in %APPDATA%/Gota (no audio is stored)."""
import json, os, time, uuid
from pathlib import Path

ROOT = Path(os.environ.get("GOTA_HOME") or (Path(os.environ.get("APPDATA", Path.home())) / "Gota"))
ROOT.mkdir(parents=True, exist_ok=True)
(ROOT / "chats").mkdir(exist_ok=True)
VOICE_CHAT = "voice"


def _read(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(path, data):
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


class Profile:
    """Name, how to be addressed, learned facts and short notes about past calls."""
    path = ROOT / "profile.json"

    def __init__(self):
        self.d = {"name": "", "treatment": "senhor", "facts": [], "call_notes": []}
        self.d.update(_read(self.path, {}))

    def save(self):
        _write(self.path, self.d)

    @property
    def is_set(self): return bool(self.d["name"].strip())
    @property
    def name(self): return self.d["name"].strip()
    @property
    def treatment(self): return self.d["treatment"]

    def set_name(self, name, treatment):
        self.d["name"], self.d["treatment"] = name.strip().title(), treatment
        self.save()

    def address(self):
        t = self.treatment
        return self.name if not t else f"{t} {self.name}"

    def sir(self):
        return self.treatment or self.name or "senhor"

    def pronoun(self):
        return {"senhor": "o senhor", "senhora": "a senhora"}.get(self.treatment, "você")

    def remember(self, fact):
        fact = fact.strip().rstrip(".")
        if len(fact) < 3:
            return
        facts = [f for f in self.d["facts"] if f.lower() != fact.lower()] + [fact]
        self.d["facts"] = facts[-40:]
        self.save()

    def add_call_note(self, note):
        note = note.strip()
        if len(note) < 5:
            return
        self.d["call_notes"] = (self.d["call_notes"] + [note[:300]])[-10:]
        self.save()


class Chats:
    def path(self, cid): return ROOT / "chats" / f"{cid}.json"

    def get(self, cid):
        return _read(self.path(cid), None)

    def _new(self, cid, title):
        chat = {"id": cid, "title": title, "updated": time.time(), "messages": []}
        _write(self.path(cid), chat)
        return chat

    def create(self, title="Nova conversa"):
        return self._new(uuid.uuid4().hex, title)

    def voice(self):
        return self.get(VOICE_CHAT) or self._new(VOICE_CHAT, "Conversas por voz")

    def append(self, cid, role, text, image=None):
        chat = self.get(cid) or self._new(cid, "Nova conversa")
        chat["messages"].append({"role": role, "text": text, "image": image, "time": time.time()})
        chat["updated"] = time.time()
        if chat["title"] == "Nova conversa" and role == "user" and text.strip():
            chat["title"] = text[:40] + ("…" if len(text) > 40 else "")
        _write(self.path(cid), chat)
        return chat

    def list(self):
        chats = [c for c in (_read(p, None) for p in (ROOT / "chats").glob("*.json")) if c]
        return sorted(chats, key=lambda c: (c["id"] != VOICE_CHAT, -c["updated"]))

    def delete(self, cid):
        self.path(cid).unlink(missing_ok=True)


class Settings:
    path = ROOT / "settings.json"

    def __init__(self):
        self.d = {"model_path": "", "hotkey": "ctrl+alt+g", "hey_gota": False, "aliases": {}, "tutorial": False, "current_chat": ""}
        self.d.update(_read(self.path, {}))

    def save(self): _write(self.path, self.d)
    def get(self, k): return self.d.get(k)

    def set(self, k, v):
        self.d[k] = v
        self.save()
