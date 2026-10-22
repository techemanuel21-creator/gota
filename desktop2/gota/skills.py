"""Skills: step-by-step procedures the assistant loads when a request matches them.

A skill is a folder with a SKILL.md: a short header (name, description, keywords) and the procedure. Skills that ship with Gota live in
gota/skills; yours live in %APPDATA%/Gota/skills (same format). When you ask for something, the best matches are handed to the model
together with the question, so it follows a proven procedure instead of improvising."""
import math, re, sys
from collections import Counter
from pathlib import Path
from .kb import words
from .store import ROOT

USER_DIR = ROOT / "skills"
MAX_BODY = 6000
TEMPLATE = """---
name: {name}
description: Uma frase dizendo QUANDO usar esta habilidade (ex.: quando um backup falhar com erro de VSS).
keywords: palavras, que, ajudam, a, achar, esta, habilidade
---
# Título do procedimento

1. Primeiro passo (explique o que olhar).
2. Segundo passo, com o comando exato em bloco de código:

```powershell
Get-Service | Where-Object Status -eq Running
```

3. Como confirmar que resolveu e o que fazer se não resolver.
"""


def bundled_dir():
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) / "gota" / "skills" if base else Path(__file__).resolve().parent / "skills"


def parse(text, fallback_name=""):
    """{'name','description','keywords','body'} from a SKILL.md ('---' header, then the procedure)."""
    meta, body = {}, text.replace("\r\n", "\n")
    m = re.match(r"\s*---\n(.*?)\n---\n?(.*)\Z", body, re.S)
    if m:
        for line in m.group(1).split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip().lower()] = v.strip()
        body = m.group(2)
    return {"name": meta.get("name") or fallback_name, "description": meta.get("description", ""), "keywords": meta.get("keywords", ""), "body": body.strip()}


def validate(skill):
    """Problems that would make a skill useless or risky; empty list = fine."""
    problems = []
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,48}", skill.get("name", "")):
        problems.append("o nome deve ter só letras minúsculas, números e hífen (ex.: veeam-falha-de-job)")
    if len(skill.get("description", "")) < 20:
        problems.append("a descrição precisa dizer quando usar a habilidade (mínimo 20 caracteres)")
    if len(skill.get("body", "")) < 80:
        problems.append("o procedimento está curto demais")
    if len(skill.get("body", "")) > MAX_BODY:
        problems.append(f"o procedimento passa de {MAX_BODY} caracteres")
    return problems


def load_all():
    """Every valid skill: yours first (they win over a bundled one with the same name), then the ones that ship with Gota."""
    found, seen = [], set()
    for source, folder in (("sua", USER_DIR), ("embutida", bundled_dir())):
        if not folder.exists():
            continue
        for f in sorted(folder.glob("*/SKILL.md")):
            try:
                sk = parse(f.read_text("utf-8"), f.parent.name)
            except OSError:
                continue
            if sk["name"] in seen or validate(sk):
                continue
            seen.add(sk["name"])
            sk["source"], sk["path"] = source, str(f)
            found.append(sk)
    return found


def search(query, k=2, min_score=3.0):
    """The skills that fit the request best: [(score, skill)]. Header words count triple; the body counts once."""
    q = set(words(query))
    skills = load_all()
    if not q or not skills:
        return []
    docs = [Counter(words((s["name"].replace("-", " ") + " " + s["description"] + " " + s["keywords"] + " ") * 3 + s["body"])) for s in skills]
    n = len(docs)
    avg = sum(sum(c.values()) for c in docs) / n
    df = Counter(w for c in docs for w in c)
    out = []
    for s, c in zip(skills, docs):
        length = sum(c.values())
        score = 0.0
        for w in q:
            if w in c:
                idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                score += idf * c[w] * 2.2 / (c[w] + 1.2 * (0.25 + 0.75 * length / avg))
        if score >= min_score:
            out.append((score, s))
    out.sort(key=lambda x: -x[0])
    return out[:k]


def prompt_block(hits, limit=1500):
    """The matched skills as text for the model's prompt."""
    return "\n\n".join(f"[HABILIDADE: {s['name']}] {s['description']}\n{s['body'][:limit]}" for _, s in hits)


def create(name):
    """Starts a new skill of yours from the template. Returns the SKILL.md path."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:48] or "nova-habilidade"
    folder = USER_DIR / slug
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "SKILL.md"
    if not path.exists():
        path.write_text(TEMPLATE.format(name=slug), "utf-8")
    return path
