"""Memory that lives across conversations: who the user is, how he likes things done, what his projects/environment are and where things are.
Saved by Gota itself from what the user says (no model call, so no delay), shown to him in the Memória window where he can edit or delete anything."""
import re, threading, time, uuid
from .store import ROOT, _read, _write
from . import tools

PATH = ROOT / "memory.json"
TYPES = ("user", "feedback", "project", "reference")
LABELS = {"user": "Sobre você", "feedback": "Como você gosta", "project": "Seus ambientes e projetos", "reference": "Onde achar"}
MAX_ITEMS = 200

_QUESTION = re.compile(r"\?\s*$|^\s*(qual|quais|quem|quando|onde|como|por que|porque|o que|quanto|voce|você|pode|consegue)\b", re.I)
_USER = re.compile(r"\b(eu sou|sou (o|a|um|uma)|trabalho (com|na|no|como|em)|moro (em|no|na)|minha empresa|meu cargo|minha equipe|me chamo|sou responsável|cuido d[eo])\b", re.I)
_FEEDBACK = re.compile(r"\b(prefiro|gosto (de|que)|n[aã]o gosto|nunca|sempre|n[aã]o (quero|use|usa|fa[cç]a|fale|precisa)|evite|pare de|odeio|detesto|quero que (você|voce|o gota))\b", re.I)
_PROJECT = re.compile(r"\b(nosso|nossa|nossos|nossas|usamos|temos|na empresa|no cliente|nosso ambiente)\b.*\b(veeam|vmware|vcenter|esxi|hyper-?v|nutanix|cisco|fortigate|pfsense|mikrotik|servidor(es)?|switch|vlan|rede|backup|dom[ií]nio|active directory|firewall|cluster|storage)\b", re.I)
_URL = re.compile(r"https?://\S+")
_lock = threading.Lock()


def _tokens(text):
    return {w for w in tools.norm(text).split() if len(w) > 2}


def _similar(a, b):
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta and tb) and len(ta & tb) / len(ta | tb)


class Memory:
    def __init__(self, path=PATH):
        self.path = path

    def items(self):
        return _read(self.path, {"items": []}).get("items", [])

    def _save(self, items):
        _write(self.path, {"items": items[-MAX_ITEMS:]})

    def add(self, kind, text):
        """Stores a memory; a very similar one of the same kind is updated instead of duplicated. Returns the stored item."""
        text = " ".join(str(text).split())[:300]
        if len(text) < 6 or kind not in TYPES:
            return None
        with _lock:
            items = self.items()
            for it in items:
                if it["type"] == kind and (_similar(it["text"], text) >= 0.6 or it["text"].lower() == text.lower()):
                    it["text"], it["updated"] = text, time.time()
                    self._save(items)
                    return it
            it = {"id": uuid.uuid4().hex[:8], "type": kind, "text": text, "created": time.time(), "updated": time.time()}
            items.append(it)
            self._save(items)
            return it

    def update(self, mid, text):
        with _lock:
            items = self.items()
            for it in items:
                if it["id"] == mid:
                    it["text"], it["updated"] = " ".join(str(text).split())[:300], time.time()
            self._save(items)

    def delete(self, mid):
        with _lock:
            self._save([it for it in self.items() if it["id"] != mid])

    def search(self, query, k=5):
        q = _tokens(query)
        scored = []
        for it in self.items():
            overlap = len(q & _tokens(it["text"]))
            if overlap:
                scored.append((overlap + (0.3 if it["type"] in ("user", "feedback") else 0), it))
        scored.sort(key=lambda x: (-x[0], -x[1]["updated"]))
        return [it for _s, it in scored[:k]]

    def block(self, query, limit=650):
        """A few lines for the prompt: how the user likes things done (always), plus what matches the question. Small on purpose: it costs time on every message."""
        items = self.items()
        picked = [it for it in sorted(items, key=lambda i: -i["updated"]) if it["type"] in ("feedback", "user")][:4]
        for it in self.search(query, 3):
            if it not in picked:
                picked.append(it)
        text = "\n".join(f"- {it['text']}" for it in picked)
        return text[:limit]

    def capture(self, message):
        """Saves what the user just said when it is a statement about himself, a preference, his environment or a link. Returns the items saved."""
        msg = " ".join(str(message).split())
        if not msg or len(msg) > 400 or _QUESTION.search(msg):
            return []
        saved = []
        for kind, rx in (("feedback", _FEEDBACK), ("user", _USER), ("project", _PROJECT)):
            if rx.search(msg):
                it = self.add(kind, msg)
                if it:
                    saved.append(it)
                break
        if _URL.search(msg) and re.search(r"\b(documenta[cç][aã]o|manual|guia|painel|dashboard|wiki|reposit[oó]rio|console)\b", msg, re.I):
            it = self.add("reference", msg)
            if it:
                saved.append(it)
        return saved

    @staticmethod
    def guess(text):
        """The kind of memory for a line the user typed himself."""
        return "feedback" if _FEEDBACK.search(text) else "project" if _PROJECT.search(text) else "reference" if _URL.search(text) else "user"

    def import_profile_facts(self, facts):
        """The facts the old profile kept become 'user' memories (once)."""
        have = {it["text"].lower() for it in self.items()}
        for f in facts:
            if f.lower() not in have:
                self.add("user", f)
