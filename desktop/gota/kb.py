"""Gota's knowledge base: notes it keeps on disk, searched by relevance (BM25), and filled by itself from the web
when it does not know something. Everything is plain text in %APPDATA%/Gota/kb, so it can be read, edited or deleted."""
import json, math, re, time
from collections import Counter
from pathlib import Path
from . import tools
from .store import ROOT

KB_DIR = ROOT / "kb"
KB_DIR.mkdir(exist_ok=True)
SEED_DIR = Path(__file__).resolve().parent / "seed"
CHUNK = 900
STOP = set("a o as os de da do das dos e em um uma que para por com no na nos nas se ao como mais mas ou ser foi sao the of and to in is it".split())


def _frozen_seed():
    import sys
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) / "gota" / "seed" if base else SEED_DIR


def words(text):
    return [w for w in tools.norm(text).split() if len(w) > 1 and w not in STOP]


def install_seed():
    """Copies the built-in expert notes (security, infrastructure, Windows, Linux, Veeam...) on first run."""
    src = _frozen_seed()
    if not src.exists():
        return
    for f in src.glob("*.md"):
        dst = KB_DIR / f.name
        if not dst.exists():
            dst.write_text(f.read_text("utf-8"), "utf-8")


def _slug(title):
    return re.sub(r"[^a-z0-9]+", "-", tools.norm(title))[:60].strip("-") or "nota"


def add(title, text, source=""):
    """Saves a note (replaces one with the same title). Returns its file."""
    path = KB_DIR / f"{_slug(title)}.md"
    path.write_text(f"# {title}\nFonte: {source or 'anotação do usuário'}\nSalvo em: {time.strftime('%d/%m/%Y')}\n\n{text.strip()}\n", "utf-8")
    return path


def _chunks():
    for f in sorted(KB_DIR.glob("*.md")):
        text = f.read_text("utf-8", "ignore")
        title = text.splitlines()[0].lstrip("# ").strip() if text else f.stem
        source = next((l[7:].strip() for l in text.splitlines()[:4] if l.startswith("Fonte:")), "")
        body = text
        for i in range(0, len(body), CHUNK):
            piece = body[max(0, i - 100):i + CHUNK]
            yield title, source, piece


def search(query, k=4):
    """Top chunks for the question: [(score, title, source, text)]. Scores around 3+ mean a real match."""
    q = words(query)
    docs = list(_chunks())
    if not q or not docs:
        return []
    toks = [Counter(words(t + " " + c)) for t, _, c in docs]
    n = len(docs)
    avg = sum(sum(c.values()) for c in toks) / n
    df = Counter(w for c in toks for w in c)
    out = []
    for (title, source, text), c in zip(docs, toks):
        length = sum(c.values())
        score = 0.0
        for w in set(q):
            if w in c:
                idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                score += idf * c[w] * 2.2 / (c[w] + 1.2 * (0.25 + 0.75 * length / avg))
        if score > 0:
            out.append((score, title, source, text))
    out.sort(key=lambda x: -x[0])
    seen, best = set(), []
    for s in out:
        if (s[1], s[3][:60]) not in seen:
            seen.add((s[1], s[3][:60]))
            best.append(s)
    return best[:k]


def good_enough(hits, query):
    """True when the best chunk covers most of the question's rare words."""
    if not hits:
        return False
    q = set(words(query))
    covered = sum(1 for w in q if w in set(words(hits[0][3] + " " + hits[0][1])))
    return hits[0][0] >= 4.0 and covered >= max(1, math.ceil(len(q) * 0.5))


DOC_HOSTS = ("docs.", "documentation", "readthedocs", "learn.microsoft.com", "developer.mozilla.org", "docs.python.org", "python.org", "nodejs.org", "developer.", "devdocs.io",
             "github.com", "kubernetes.io", "docs.docker.com", "man7.org", "wikipedia.org", "veeam.com", "access.redhat.com", "ubuntu.com", "archlinux.org")


def _doc_rank(url):
    """Official-looking documentation first (docs sites, vendor knowledge bases, READMEs), blogs and forums later."""
    u = url.lower()
    return 0 if any(h in u for h in DOC_HOSTS) else 1


def _page_text(raw):
    """The readable text of a page: headings and paragraphs as lines, code blocks (<pre>) with their line breaks kept."""
    raw = re.sub(r"<(script|style|nav|header|footer|aside|form|svg|noscript)[\s\S]*?</\1>", " ", raw, flags=re.I)
    out = []
    for m in re.finditer(r"<(pre|p|li|h[1-4]|td)[^>]*>([\s\S]*?)</\1>", raw, flags=re.I):
        tag, body = m.group(1).lower(), m.group(2)
        if tag == "pre":
            code = re.sub(r"<br\s*/?>", "\n", body, flags=re.I)
            code = __import__("html").unescape(re.sub(r"<[^>]+>", "", code)).strip("\n")
            if 20 < len(code) < 2500:
                out.append("```\n" + code + "\n```")
        else:
            t = tools._strip(body)
            if len(t) > 40 or (tag.startswith("h") and len(t) >= 2):
                out.append(("## " if tag.startswith("h") else "") + t)
    return "\n".join(out)


GENERIC = set("biblioteca bibliotecas library libraries documentacao documentation docs oficial official guia guide tutorial como usar uso fazer criar tecnica tecnicas "
               "sobre para com uma uns umas the how use using about with api referencia reference exemplo exemplos example examples".split())


def keywords(text, limit=8):
    """The words that identify a technical subject (generic words like 'documentation' or 'biblioteca' dropped)."""
    out = []
    for w in tools.norm(text).split():
        if len(w) > 2 and w not in STOP and w not in GENERIC and w not in out:
            out.append(w)
    return out[:limit]


def relevance(text, kws):
    """Share of the subject's keywords that really appear in the page (1.0 when the subject has no keywords)."""
    if not kws:
        return 1.0
    have = set(tools.norm(text[:30000]).split())
    return sum(1 for k in kws if k in have) / len(kws)


def learn(topic, on_status=lambda s: None, max_pages=4, queries=None):
    """Looks the topic up on the internet (official documentation first), reads the best pages and keeps them as notes in the knowledge
    base, so from then on the answer is known. Returns the titles saved (empty if offline or nothing useful)."""
    if not tools.is_online():
        return []
    on_status("Procurando a documentação na internet...")
    found = []
    kws = keywords(topic + " " + " ".join(queries or []))
    if len(kws) > 3 and queries is not None:   # fixed queries (document packs): the subject alone says what the page must be about
        kws = keywords(topic)[:3]
    for q in (queries or [topic + " documentação oficial", topic + " official documentation", topic + " guia tutorial"]):
        try:
            page = tools._bing(q)
        except Exception:
            continue
        for block in re.findall(r'<li class="b_algo"[\s\S]*?</li>', page):
            title_m = re.search(r"<h2[^>]*>([\s\S]*?)</h2>", block)
            for href in re.findall(r'href="(https?://[^"]+)"', block):
                url = tools._real_url(href)
                if url and url not in [u for u, _ in found] and "youtube.com" not in url and not url.endswith(".pdf"):
                    found.append((url, tools._strip(title_m.group(1)) if title_m else url))
                    break
        if len(found) >= max_pages + 2:
            break
    found.sort(key=lambda x: _doc_rank(x[0]))   # stable: documentation sites first, search order kept inside each group
    saved = []
    for url, title in found:
        if len(saved) >= max_pages:
            break
        on_status("Lendo e guardando: " + title[:50])
        try:
            raw = tools.http(url, timeout=10, limit=700_000).decode("utf-8", "ignore")
        except Exception:
            continue
        text = _page_text(raw)
        if len(text) > 400 and relevance(text, kws) >= 0.6:   # keep only pages that really are about the subject
            add(f"{topic} — {title[:60]}", text[:12000], url)
            saved.append(title)
    return saved


def learn_package(name, ecosystem="python", on_status=lambda s: None):
    """A programming library: its README (usage examples included) straight from the package registry (PyPI or npm), plus its documentation
    site when the registry points to one. Far more reliable than a web search. Returns the titles saved."""
    import json, urllib.parse
    name = re.sub(r"[^A-Za-z0-9_.@/-]", "", str(name))[:80]
    if not name or not tools.is_online():
        return []
    saved = []
    try:
        if ecosystem == "python":
            on_status(f"Lendo {name} no PyPI...")
            info = json.loads(tools.http(f"https://pypi.org/pypi/{name}/json", timeout=12, limit=3_000_000).decode("utf-8", "ignore"))["info"]
            text = f"{info.get('summary') or ''}\n\n{info.get('description') or ''}".strip()
            if len(text) > 200:
                add(f"{name} (Python) — README", text[:14000], f"https://pypi.org/project/{name}/")
                saved.append(f"{name} (README no PyPI)")
            urls = info.get("project_urls") or {}
            docs = next((u for k, u in urls.items() if "doc" in k.lower()), None) or info.get("docs_url")
            source = f"https://pypi.org/project/{name}/"
        else:
            on_status(f"Lendo {name} no npm...")
            data = json.loads(tools.http(f"https://registry.npmjs.org/{urllib.parse.quote(name, safe='@')}", timeout=12, limit=3_000_000).decode("utf-8", "ignore"))
            text = (data.get("readme") or "").strip()
            if len(text) > 200:
                add(f"{name} (npm) — README", text[:14000], f"https://www.npmjs.com/package/{name}")
                saved.append(f"{name} (README no npm)")
            docs = data.get("homepage")
            source = f"https://www.npmjs.com/package/{name}"
        if docs and docs.startswith("http") and "github.com" not in docs:
            on_status("Lendo a documentação do site oficial...")
            page = _page_text(tools.http(docs, timeout=12, limit=700_000).decode("utf-8", "ignore"))
            if len(page) > 400 and relevance(page, keywords(name)) >= 1.0:
                add(f"{name} — documentação", page[:12000], docs)
                saved.append(f"{name} (documentação oficial)")
    except Exception:
        pass
    return saved


def learn_if_needed(topic, on_status=lambda s: None, queries=None):
    """Learns `topic` only when the knowledge base does not already cover it. Returns the titles learned now ([] if it already knew or could not learn)."""
    hits = search(topic, 3)
    if good_enough(hits, topic):
        return []
    return learn(topic, on_status, queries=queries)


def listing():
    return [f.stem for f in sorted(KB_DIR.glob("*.md"))]
