"""WhatsApp inside Gota: you scan the QR code once in a window Gota opens (WhatsApp Web), and from then on Gota can send messages and
pictures to your contacts by name. The session lives only in a private Edge profile on this computer (%APPDATA%/Gota/whatsapp).
Unofficial: it drives WhatsApp Web like a person would, so WhatsApp's page changes can break it."""
import re, unicodedata
import ctypes, shutil, struct, time
from pathlib import Path
from .store import ROOT

PROFILE = ROOT / "whatsapp"
URL = "https://web.whatsapp.com/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0"



def _phon(word):
    """A rough sound-alike key for a name, so spellings such as Emanuel / Emmanuel / Emanoel compare equal."""
    w = unicodedata.normalize("NFKD", word.lower()).encode("ascii", "ignore").decode()
    w = re.sub(r"[^a-z]", "", w)
    for a, b in (("ph", "f"), ("th", "t"), ("ck", "k"), ("ch", "x"), ("y", "i"), ("w", "u"), ("k", "c"), ("oe", "ue"), ("h", "")):
        w = w.replace(a, b)
    return re.sub(r"(.)\1+", r"\1", w)


def name_variants(contact, names=()):
    """The contact as asked first, then likely spellings: the owner's own spelling when the name sounds like his, doubled or single letters,
    ph/f, y/i, w/u. At most 8, no repeats."""
    contact = " ".join(contact.split())
    out = [contact]
    words = contact.split()
    for known in names:
        for k in str(known).split():
            for i, w in enumerate(words):
                if _phon(w) == _phon(k) and w.lower() != k.lower():
                    out.append(" ".join(words[:i] + [k.capitalize() if w[:1].isupper() else k] + words[i + 1:]))
    out.append(re.sub(r"(.)\1+", r"\1", contact, flags=re.I))
    for a, b in (("mm", "m"), ("m", "mm"), ("nn", "n"), ("n", "nn"), ("ph", "f"), ("f", "ph"), ("y", "i"), ("i", "y"), ("w", "u"), ("th", "t"), ("oe", "ue"), ("ue", "oe")):
        v = re.sub(a, b, contact, count=1, flags=re.I)
        out.append(v)
    seen, res = set(), []
    for v in out:
        if v.lower() not in seen:
            seen.add(v.lower())
            res.append(v)
    return res[:8]

class NotConnected(Exception):
    pass


class Cancelled(Exception):
    pass


def copy_image_to_clipboard(path):
    """Puts a picture on the Windows clipboard (as a DIB) so WhatsApp Web can paste it like a person would."""
    from io import BytesIO
    from PIL import Image
    img = Image.open(path).convert("RGB")
    buf = BytesIO()
    img.save(buf, "BMP")
    dib = buf.getvalue()[14:]  # a clipboard DIB is a BMP without its 14-byte file header
    u, k = ctypes.windll.user32, ctypes.windll.kernel32
    k.GlobalAlloc.restype = ctypes.c_void_p
    k.GlobalLock.restype = ctypes.c_void_p
    u.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    for _ in range(10):
        if u.OpenClipboard(None):
            break
        time.sleep(0.1)
    else:
        raise OSError("área de transferência ocupada")
    try:
        u.EmptyClipboard()
        h = k.GlobalAlloc(0x2002, len(dib))  # GMEM_MOVEABLE | GMEM_DDESHARE
        p = k.GlobalLock(ctypes.c_void_p(h))
        ctypes.memmove(p, dib, len(dib))
        k.GlobalUnlock(ctypes.c_void_p(h))
        u.SetClipboardData(8, h)  # CF_DIB
    finally:
        u.CloseClipboard()


class WhatsApp:
    def __init__(self, settings):
        self.settings = settings

    def connected(self):
        return bool(self.settings.get("whatsapp_connected")) and PROFILE.exists()

    # ------------------------------------------------------------------ browser
    def _open(self, pw, headless):
        PROFILE.mkdir(parents=True, exist_ok=True)
        opts = dict(user_data_dir=str(PROFILE), channel="msedge", headless=headless, locale="pt-BR", viewport={"width": 1280, "height": 820},
                    args=["--disable-blink-features=AutomationControlled"], ignore_default_args=["--enable-automation"])
        if headless:
            opts["user_agent"] = UA  # WhatsApp Web refuses browsers that call themselves "Headless"
        try:
            return pw.chromium.launch_persistent_context(**opts)
        except Exception as e:
            raise RuntimeError("Não consegui abrir o Microsoft Edge (ele precisa estar instalado e fechado se usar o mesmo perfil): " + str(e)[:150])

    @staticmethod
    def _state(page, timeout):
        """'ready' (chat list visible), 'qr' (asking for the QR code) or 'unknown'."""
        end = time.time() + timeout
        seen_qr = 0
        while time.time() < end:
            if page.query_selector("#pane-side"):
                return "ready"
            if page.query_selector("canvas[aria-label], div[data-ref]"):
                seen_qr += 1
                if seen_qr >= 3:
                    return "qr"
            time.sleep(1)
        return "qr" if seen_qr else "unknown"

    # ------------------------------------------------------------------ connect / disconnect
    def connect(self, on_status=lambda s: None, wait=240):
        """Opens WhatsApp Web in a visible window; the user scans the QR code. Returns True when the chat list shows up."""
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            ctx = self._open(pw, headless=False)
            try:
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                page.goto(URL)
                on_status("Escaneie o QR code com o seu celular: WhatsApp > Aparelhos conectados > Conectar um aparelho.")
                end = time.time() + wait
                while time.time() < end:
                    if page.query_selector("#pane-side"):
                        on_status("Conectado! Sincronizando as conversas…")
                        time.sleep(8)  # let the session settle before closing
                        self.settings.set("whatsapp_connected", True)
                        return True
                    time.sleep(1)
                return False
            finally:
                ctx.close()

    def disconnect(self):
        self.settings.set("whatsapp_connected", False)
        shutil.rmtree(PROFILE, ignore_errors=True)

    # ------------------------------------------------------------------ send
    SEARCH = 'input[data-tab="3"], input[role="textbox"][aria-label*="esquis"], input[role="textbox"][aria-label*="earch"], div[contenteditable="true"][data-tab="3"]'
    COMPOSER = '#main footer div[role="textbox"][contenteditable="true"], footer div[contenteditable="true"]'

    @staticmethod
    def _dismiss_popups(page):
        """WhatsApp Web sometimes puts its own pop-ups ("what's new"...) over the page and they swallow every click: close them."""
        for _ in range(4):
            dlg = page.locator('[role="dialog"]')
            if not dlg.count():
                return
            ok = dlg.locator('button:has-text("Continuar"), button:has-text("Continue"), button:has-text("OK"), button:has-text("Entendi"), '
                             'button[aria-label="Fechar"], button[aria-label="Close"]')
            try:
                if ok.count():
                    ok.first.click(timeout=4000)
                else:
                    page.keyboard.press("Escape")
            except Exception:
                page.keyboard.press("Escape")
            time.sleep(1)

    def _open_chat(self, page, contact, names=()):
        """Searches the contact by name and opens the top result like a person would (type, Enter). Names are often written differently from how they
        sound (Emanuel / Emmanuel), so spelling variants are tried too. Returns the name shown in the chat header."""
        search = page.locator(self.SEARCH).first
        main = page.locator("#main")
        for query in name_variants(contact, names):
            search.click(timeout=15000)
            page.keyboard.press("Control+A")
            page.keyboard.insert_text(query)
            time.sleep(2.2)
            page.keyboard.press("Enter")
            opened = False
            for attempt in range(2):
                try:
                    main.first.wait_for(timeout=4000)
                    opened = True
                    break
                except Exception:
                    if not attempt:
                        page.keyboard.press("ArrowDown")   # the first row can be a section title
                        page.keyboard.press("Enter")
            if opened:
                break
        else:
            raise RuntimeError(f"Não encontrei nenhum contato ou conversa chamado “{contact}” (tentei também outras grafias do nome).")
        page.locator(self.COMPOSER).first.wait_for(timeout=15000)
        header = page.locator("#main header span[dir='auto']").first
        try:
            return header.inner_text(timeout=5000).strip() or contact
        except Exception:
            return contact

    @staticmethod
    def _attach_photo(page, image):
        """Puts the picture in the chat as a PHOTO: through the paperclip menu's "Photos & videos" item, like a person; if the menu is not found,
        through the page's photo file input. Never the sticker input, which would send it as a sticker."""
        try:
            page.locator('[aria-label="Anexar"], [aria-label="Attach"], span[data-icon="plus-rounded"], span[data-icon="plus"], span[data-icon="attach-menu-plus"]').first.click(timeout=5000)
            item = page.locator('li:has-text("Fotos e vídeos"), [role="menuitem"]:has-text("Fotos"), li:has-text("Photos"), [role="menuitem"]:has-text("Photos")').first
            with page.expect_file_chooser(timeout=6000) as chooser:
                item.click(timeout=5000)
            chooser.value.set_files(str(image))
            return
        except Exception:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
        accepts = page.eval_on_selector_all('input[type="file"]', "els => els.map(e => e.getAttribute('accept') || '')")
        idx = next((i for i, a in enumerate(accepts) if "video" in a), None)
        if idx is None:
            idx = next((i for i, a in enumerate(accepts) if "image" in a and "webp" not in a), None)
        if idx is None:
            raise RuntimeError("Não achei o campo de fotos do WhatsApp (a página mudou?).")
        page.locator('input[type="file"]').nth(idx).set_input_files(str(image))

    _UNREAD_JS = """
    () => {
      const seen = new Map();
      const rows = document.querySelectorAll('#pane-side [role="listitem"], #pane-side [role="row"], #pane-side [data-testid="cell-frame-container"]');
      rows.forEach(row => {
        const badge = row.querySelector('[aria-label*="não lida"], [aria-label*="nao lida"], [aria-label*="unread"], [data-testid="icon-unread-count"]');
        if (!badge) return;
        const title = (row.querySelector('span[title]') || {}).title || '';
        const m = ((badge.getAttribute('aria-label') || badge.innerText || '') + '').match(/\\d+/);
        if (title && !seen.has(title)) seen.set(title, m ? parseInt(m[0]) : 1);
      });
      return [...seen.entries()].map(([title, count]) => ({title, count}));
    }
    """

    def unread(self, on_status=lambda s: None):
        """The chats with unread messages, read from the connected WhatsApp Web: [{title, count}] (newest first as the list shows them).
        Uses the "Não lidas" filter when the page has it, so chats below the visible part of the list are counted too."""
        from playwright.sync_api import sync_playwright
        if not self.connected():
            raise NotConnected()
        with sync_playwright() as pw:
            ctx = self._open(pw, headless=True)
            try:
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                on_status("Abrindo o WhatsApp…")
                page.goto(URL)
                state = self._state(page, 75)
                if state == "qr":
                    self.settings.set("whatsapp_connected", False)
                    raise NotConnected()
                if state != "ready":
                    raise RuntimeError("O WhatsApp Web não carregou a tempo.")
                time.sleep(2)
                self._dismiss_popups(page)
                on_status("Lendo as conversas não lidas…")
                try:   # the filter chip shows only the unread chats
                    page.locator('button:has-text("Não lidas"), [role="button"]:has-text("Não lidas"), button:has-text("Unread"), [role="button"]:has-text("Unread")').first.click(timeout=3000)
                    time.sleep(1.2)
                except Exception:
                    pass
                found = {}
                for _ in range(6):   # scroll the list so rows below the visible part are read too
                    for r in page.evaluate(self._UNREAD_JS):
                        found.setdefault(r["title"], r["count"])
                    try:
                        before = len(found)
                        page.evaluate("() => { const p = document.querySelector('#pane-side'); if (p) p.scrollBy(0, p.clientHeight * 0.9); }")
                        time.sleep(0.5)
                        if before == len(found) and _ >= 1:
                            break
                    except Exception:
                        break
                return [{"title": k, "count": v} for k, v in found.items()]
            finally:
                ctx.close()

    def send(self, contact, message="", image=None, confirm=lambda found: True, on_status=lambda s: None, dry_run=False, names=()):
        """Finds `contact` by name, asks confirm(found_name), then sends the picture and/or the text. Returns the contact's name as WhatsApp shows it.
        dry_run does everything except the final send (and cleans up): used to check that the page still looks the way this code expects."""
        from playwright.sync_api import sync_playwright
        if not self.connected():
            raise NotConnected()
        with sync_playwright() as pw:
            ctx = self._open(pw, headless=True)
            try:
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                on_status("Abrindo o WhatsApp…")
                page.goto(URL)
                state = self._state(page, 75)
                if state == "qr":
                    self.settings.set("whatsapp_connected", False)
                    raise NotConnected()
                if state != "ready":
                    raise RuntimeError("O WhatsApp Web não carregou a tempo.")
                time.sleep(2)
                self._dismiss_popups(page)
                on_status(f"Procurando {contact}…")
                found = self._open_chat(page, contact, names)
                self._dismiss_popups(page)
                answer = confirm(found)   # True/False, or (True/False, edited text) when the user may rewrite the message
                ok, edited = answer if isinstance(answer, tuple) else (answer, None)
                if not ok:
                    raise Cancelled()
                if edited is not None:
                    message = edited.strip()
                on_status(f"Enviando para {found}…")
                if image:
                    # a picture goes through the chat's own file picker, then its Send button
                    self._attach_photo(page, image)
                    send_btn = page.locator('[role="button"][aria-label^="Enviar"], [aria-label^="Send"]').first
                    send_btn.wait_for(timeout=20000)
                    time.sleep(1)
                    if dry_run:   # throw the test picture away instead of sending it
                        page.keyboard.press("Escape")
                        discard = page.locator('[role="dialog"] button:has-text("Descartar"), [role="dialog"] button:has-text("Discard")')
                        try:
                            discard.first.click(timeout=5000)
                        except Exception:
                            pass
                        time.sleep(1)
                    else:
                        send_btn.click(timeout=8000)
                        time.sleep(3)
                if message:
                    box = page.locator(self.COMPOSER).first
                    box.click(timeout=10000)
                    page.keyboard.insert_text(message)
                    if dry_run:
                        page.keyboard.press("Control+A")
                        page.keyboard.press("Delete")
                    else:
                        page.keyboard.press("Enter")
                time.sleep(2.5 if not dry_run else 0.5)   # let it leave the outbox
                return found
            finally:
                ctx.close()
