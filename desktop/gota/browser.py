"""A general browser for the agent: open any site, read its structure (not only text), click, type, scroll, take pictures, see console errors and
network requests, and test a page at phone / tablet / desktop size. Playwright drives Edge with its own profile (%APPDATA%\\Gota\\browser), kept
between uses, so a login the user makes himself in the visible window stays. Playwright's objects live on ONE thread: everything is queued to it."""
import queue, re, threading, time
from pathlib import Path
from .store import ROOT

PROFILE = ROOT / "browser"
PRESETS = {"mobile": (390, 844), "tablet": (820, 1180), "desktop": (1366, 768)}
RISKY = re.compile(r"\b(enviar|send|submit|comprar|buy|pagar|pay|checkout|finalizar|confirmar|confirm|deletar|delete|apagar|excluir|remove|publicar|publish|post|assinar|subscribe|transferir|transfer|aceitar|accept|concordo|agree)\b", re.I)

_SNAPSHOT_JS = """
() => {
  const vis = el => { const r = el.getBoundingClientRect(), s = getComputedStyle(el); return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const sel = 'a[href],button,input,select,textarea,summary,[role=button],[role=link],[role=tab],[role=menuitem],[role=checkbox],[onclick]';
  let n = 0; const out = [];
  document.querySelectorAll('[data-gota-ref]').forEach(e => e.removeAttribute('data-gota-ref'));
  document.querySelectorAll(sel).forEach(el => {
    if (!vis(el) || out.length >= 80) return;
    n += 1; el.setAttribute('data-gota-ref', n);
    const label = (el.innerText || el.value || el.getAttribute('aria-label') || el.placeholder || el.title || el.alt || el.name || '').trim().replace(/\\s+/g, ' ').slice(0, 60);
    out.push(`ref ${n}  <${el.tagName.toLowerCase()}${el.type ? ' ' + el.type : ''}>  ${label}${el.href ? '  -> ' + el.href.slice(0, 70) : ''}`);
  });
  const heads = [...document.querySelectorAll('h1,h2,h3')].filter(vis).slice(0, 12).map(h => `${h.tagName.toLowerCase()}: ${h.innerText.trim().slice(0, 70)}`);
  return { title: document.title, url: location.href, headings: heads, elements: out };
}
"""


class BrowserError(Exception):
    pass


class Browser:
    def __init__(self):
        self.q = queue.Queue()
        self.thread = None
        self.console, self.requests = [], []
        self.visible = False
        self._pw = self._ctx = self.page = None

    # ---- the owner thread
    def _ensure_thread(self):
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()

    def _loop(self):
        while True:
            fn, box, done = self.q.get()
            if fn is None:
                self._shutdown()
                done.set()
                return
            try:
                box["value"] = fn()
            except Exception as e:
                box["error"] = e
            done.set()

    def run(self, fn, timeout=60):
        """Runs fn on the browser thread and returns its result (or raises its error)."""
        self._ensure_thread()
        box, done = {}, threading.Event()
        self.q.put((fn, box, done))
        if not done.wait(timeout):
            raise BrowserError("o navegador não respondeu a tempo")
        if "error" in box:
            raise box["error"]
        return box.get("value")

    # ---- session (called on the browser thread)
    def _start(self):
        if self.page is not None and not self.page.is_closed():
            return
        from playwright.sync_api import sync_playwright
        PROFILE.mkdir(parents=True, exist_ok=True)
        if self._pw is None:
            self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(str(PROFILE), channel="msedge", headless=not self.visible, viewport={"width": 1366, "height": 768},
                                                               args=["--disable-blink-features=AutomationControlled"] if self.visible else [])
        self.page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        self.page.on("console", lambda m: self.console.append(f"[{m.type}] {m.text}"[:300]) if len(self.console) < 200 else None)
        self.page.on("pageerror", lambda e: self.console.append(f"[erro da página] {e}"[:300]))
        self.page.on("response", lambda r: self.requests.append(f"{r.status} {r.request.method} {r.url[:140]}") if len(self.requests) < 300 else None)
        self.page.on("requestfailed", lambda r: self.requests.append(f"FALHOU {r.request.method if hasattr(r, 'request') else r.method} {r.url[:140]}"))

    def _shutdown(self):
        for obj in (self._ctx, self._pw):
            try:
                obj and (obj.close() if obj is self._ctx else obj.stop())
            except Exception:
                pass
        self._pw = self._ctx = self.page = None

    def close(self):
        if self.thread is not None and self.thread.is_alive():
            done = threading.Event()
            self.q.put((None, {}, done))
            done.wait(10)

    def restart(self, visible):
        self.visible = visible
        if self.thread is not None and self.thread.is_alive():
            self.run(self._shutdown)

    # ---- actions (each runs on the browser thread through run())
    def open(self, url):
        def go():
            self._start()
            self.console.clear(), self.requests.clear()
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                self.page.wait_for_load_state("networkidle", timeout=6000)
            except Exception:
                pass
            return f"{self.page.title()} — {self.page.url}"
        return self.run(go, 70)

    def snapshot(self):
        def snap():
            self._start()
            d = self.page.evaluate(_SNAPSHOT_JS)
            return (f"PÁGINA: {d['title']}\nURL: {d['url']}\nTÍTULOS:\n" + "\n".join(d["headings"]) + "\nELEMENTOS (use target=\"ref N\"):\n" + "\n".join(d["elements"]))
        return self.run(snap)

    def text(self, limit=4000):
        def read():
            self._start()
            return self.page.evaluate("() => document.body.innerText")[:limit]
        return self.run(read)

    def _locator(self, target):
        t = str(target).strip()
        m = re.match(r"^ref\s*(\d+)$", t, re.I)
        if m:
            return self.page.locator(f'[data-gota-ref="{m.group(1)}"]').first
        if t.lower().startswith("css=") or re.search(r"[#.\[\]>]", t):
            return self.page.locator(t[4:] if t.lower().startswith("css=") else t).first
        return self.page.get_by_text(t, exact=False).first

    def describe(self, target):
        """What the element is (for the permission check): its text and type."""
        def info():
            self._start()
            loc = self._locator(target)
            return loc.evaluate("e => ({tag: e.tagName.toLowerCase(), type: e.type || '', text: (e.innerText || e.value || e.getAttribute('aria-label') || '').trim().slice(0, 80), form: !!e.closest('form')})")
        return self.run(info)

    def click(self, target):
        def go():
            self._start()
            self._locator(target).click(timeout=8000)
            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
            return f"Cliquei. Agora em: {self.page.title()} — {self.page.url}"
        return self.run(go)

    def type(self, target, text, submit=False):
        def go():
            self._start()
            loc = self._locator(target)
            if (loc.evaluate("e => e.type || ''") or "").lower() == "password":
                raise BrowserError("campo de SENHA: o Gota não digita senhas. Abra a janela visível (action=show) e entre você mesmo; o login fica salvo.")
            loc.fill(str(text), timeout=8000)
            if submit:
                loc.press("Enter")
            return "Digitado."
        return self.run(go)

    def press(self, key):
        def go():
            self._start()
            self.page.keyboard.press(key)
            return f"Tecla {key}."
        return self.run(go)

    def scroll(self, direction="down"):
        def go():
            self._start()
            self.page.mouse.wheel(0, {"down": 700, "up": -700, "top": -100000, "bottom": 100000}.get(direction, 700))
            return f"Rolei ({direction})."
        return self.run(go)

    def resize(self, preset):
        w, h = PRESETS.get(preset, PRESETS["desktop"])

        def go():
            self._start()
            self.page.set_viewport_size({"width": w, "height": h})
            return f"Tamanho de tela: {preset} ({w}x{h})."
        return self.run(go)

    def screenshot(self, path=None):
        def shot():
            self._start()
            p = Path(path) if path else Path(__import__("tempfile").gettempdir()) / f"gota_browser_{int(time.time())}.png"
            self.page.screenshot(path=str(p), full_page=False)
            return str(p)
        return self.run(shot)

    def back(self):
        def go():
            self._start()
            self.page.go_back(timeout=8000)
            return f"{self.page.title()} — {self.page.url}"
        return self.run(go)
