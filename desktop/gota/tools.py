"""What Gota can do on the computer: search the web, weather, open apps, timers and the calendar."""
import time
import base64, html, json, os, re, subprocess, threading, time, unicodedata, urllib.parse, urllib.request
from datetime import datetime, timedelta
from pathlib import Path

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
NOFLASH = 0x08000000  # CREATE_NO_WINDOW


def norm(text: str) -> str:
    t = unicodedata.normalize("NFD", text.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t)).strip()


def http(url, timeout=8, limit=600_000, headers=None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(limit)


_ONLINE = {"t": 0.0, "v": False}


def mark_online():
    """Called when something that needs the internet just worked (the cloud model): skips the connectivity check for a while."""
    _ONLINE["hint"] = time.time()


def is_online() -> bool:
    """Whether the internet answers (remembered for 20 seconds, so a single question does not pay for the check several times)."""
    if time.time() - _ONLINE["t"] < 20:
        return _ONLINE["v"]
    if time.time() - _ONLINE.get("hint", 0) < 120:   # the cloud model answered a moment ago: the internet is there, no need for an extra request
        return True
    try:
        http("https://www.bing.com/robots.txt", timeout=4, limit=200)
        _ONLINE["v"] = True
    except Exception:
        _ONLINE["v"] = False
    _ONLINE["t"] = time.time()
    return _ONLINE["v"]


# ---------------------------------------------------------------- web search (Bing, free)

_REL = re.compile(r"^(\d+)\s+(minutos?|horas?|dias?|semanas?|m[eê]s|meses)\s+atr[aá]s\s*·?\s*", re.I)
_ABS = re.compile(r"^(\d{1,2}) de (jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\.? de (\d{4})\s*·?\s*", re.I)
_MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _strip(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", "", s)).replace("\xa0", " ")).strip()


def _dated(snippet: str):
    """'1 dia atrás · texto' -> ('(14/10/2026) texto', age in hours). Newest first."""
    now = datetime.now()
    m = _REL.match(snippet)
    if m:
        n, unit = int(m.group(1)), norm(m.group(2))
        hours = 0 if unit.startswith("minuto") else n if unit.startswith("hora") else n * 24 if unit.startswith("dia") \
            else n * 168 if unit.startswith("semana") else n * 720
        return f"({(now - timedelta(hours=hours)):%d/%m/%Y}) " + snippet[m.end():], hours
    m = _ABS.match(snippet)
    if m:
        day = datetime(int(m.group(3)), _MONTHS.index(norm(m.group(2))) + 1, int(m.group(1)))
        return f"({day:%d/%m/%Y}) " + snippet[m.end():], max(0, (now - day).total_seconds() / 3600)
    return snippet, 1440


def _real_url(href: str):
    href = href.replace("&amp;", "&")
    m = re.search(r"[?&]u=a1([^&]+)", href)
    if m:
        enc = m.group(1)
        try:
            return base64.urlsafe_b64decode(enc + "=" * (-len(enc) % 4)).decode("utf-8")
        except Exception:
            return None
    return href if href.startswith("http") and "bing.com" not in href else None


def _page_text(url, keywords, max_chars=1500) -> str:
    page = http(url, limit=400_000).decode("utf-8", "ignore")
    page = re.sub(r"<(script|style|nav|header|footer|aside|form)[\s\S]*?</\1>", " ", page, flags=re.I)
    paragraphs = [p for p in (_strip(x) for x in re.findall(r"<p[^>]*>([\s\S]*?)</p>", page, flags=re.I)) if len(p) > 60]
    paragraphs.sort(key=lambda p: -sum(k in norm(p) for k in keywords))
    out = ""
    for p in paragraphs:
        if len(out) + len(p) > max_chars:
            break
        out += p + " "
    return out.strip()


_STATUS = {"o", "a", "os", "as", "ja", "foi", "foram", "e", "esta", "sera", "aprovado", "aprovada", "aprovados", "aprovadas",
           "mesmo", "realmente", "verdade", "certo", "oficialmente"}


def core_query(query: str) -> str:
    """The same question without status words ('já foi aprovado'), which make Bing look for dictionary entries."""
    words = [w for w in query.split() if norm(w) not in _STATUS]
    return " ".join(words) if len(words) >= 2 else query


def _bing(query):
    return http("https://www.bing.com/search?q=" + urllib.parse.quote(query) + "&setlang=pt-BR&cc=BR&mkt=pt-BR&setmkt=pt-BR").decode("utf-8", "ignore")


def _ddg(query):
    """DuckDuckGo's plain HTML results as [(snippet, url)]: the second search engine, used when Bing gives nothing."""
    page = http("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query) + "&kl=br-pt", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}).decode("utf-8", "ignore")
    out = []
    for part in re.split(r'<div class="[^"]*results_links[^"]*"', page)[1:]:
        link = re.search(r'class="result__a"[^>]*href="([^"]+)"', part)
        snip = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', part, flags=re.S)
        if not link:
            continue
        href = link.group(1)
        m = re.search(r"uddg=([^&]+)", href)
        url = urllib.parse.unquote(m.group(1)) if m else ("https:" + href if href.startswith("//") else href)
        out.append((_strip(snip.group(1)) if snip else "", url))
    return out


def web_search(query, max_snippets=8, max_pages=2):
    """Returns (snippets newest first, page texts). Searches the question and its core words, merges, newest first. Blocking."""
    queries = [query] + ([core_query(query)] if core_query(query) != query else [])
    blocks, snippets, seen = [], [], set()
    for q in queries:
        try:
            found = re.findall(r'<li class="b_algo"[\s\S]*?</li>', _bing(q))
        except Exception:
            continue
        for b in found:
            m = re.search(r'<p class="b_lineclamp\d?"[^>]*>(.*?)</p>', b, flags=re.S)
            text = _strip(m.group(1)) if m else ""
            if text and text not in seen:
                seen.add(text)
                snippets.append(_dated(text))
            blocks.append(b)
    if not blocks:   # Bing gave nothing (blocked, new layout...): ask DuckDuckGo
        try:
            for snip, url in _ddg(query)[:8]:
                if snip and snip not in seen:
                    seen.add(snip)
                    snippets.append(_dated(snip))
                blocks.append(f'<li><a href="{url}"></a></li>')
        except Exception:
            pass
    snippets = [s for s, _ in sorted(snippets, key=lambda x: x[1])][:max_snippets]
    keywords = [w for w in norm(core_query(query)).split() if len(w) > 3]
    pages = []
    for b in blocks:
        if len(pages) >= max_pages:
            break
        for href in re.findall(r'href="(https?://[^"]+)"', b):
            url = _real_url(href)
            if url and "youtube.com" not in url and not url.endswith(".pdf"):
                try:
                    text = _page_text(url, keywords)
                    if text:
                        pages.append(text)
                except Exception:
                    pass
                break
    return snippets, pages


# ---------------------------------------------------------------- location and weather (free, no key)

_loc = {}


def location():
    """City and coordinates from the internet address (cached). None when offline."""
    if _loc:
        return _loc
    for url in ("https://ipwho.is/", "https://ipapi.co/json/"):
        try:
            d = json.loads(http(url, timeout=6))
            lat, lon = d.get("latitude"), d.get("longitude")
            if lat is not None:
                _loc.update(lat=float(lat), lon=float(lon), city=d.get("city") or "", region=d.get("region") or "")
                return _loc
        except Exception:
            continue
    return None


_SYMBOLS = {"clearsky": "céu limpo", "fair": "poucas nuvens", "partlycloudy": "parcialmente nublado", "cloudy": "nublado",
            "fog": "neblina", "rain": "chuva", "lightrain": "chuva fraca", "heavyrain": "chuva forte",
            "rainshowers": "pancadas de chuva", "lightrainshowers": "chuva leve passageira", "heavyrainshowers": "pancadas fortes de chuva",
            "rainandthunder": "chuva com trovoadas", "heavyrainandthunder": "temporal", "lightrainandthunder": "chuva fraca com trovoadas",
            "sleet": "chuva com gelo", "snow": "neve"}


def _describe(code: str) -> str:
    base = code.split("_")[0]
    return _SYMBOLS.get(base, base)


def _rainy(code: str) -> bool:
    return any(w in code for w in ("rain", "sleet", "thunder", "drizzle"))


def weather_data(lat, lon):
    d = json.loads(http(f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={lat:.4f}&lon={lon:.4f}",
                        headers={"User-Agent": "GotaDesktop/1.0 (assistant)"}))
    return d["properties"]["timeseries"]


def weather_answer(question: str, sir: str) -> str:
    loc = location()
    if not loc:
        return f"Preciso de internet para saber onde estamos e consultar o clima, {sir}."
    series = weather_data(loc["lat"], loc["lon"])
    now = series[0]["data"]["instant"]["details"]["air_temperature"]
    code1 = series[0]["data"].get("next_1_hours", {}).get("summary", {}).get("symbol_code", "")
    q = norm(question)
    city = loc.get("city") or "sua região"
    horizon = series[:12]
    rain_codes = [(datetime.fromisoformat(s["time"].replace("Z", "+00:00")).astimezone(), s["data"].get("next_1_hours", {}).get("summary", {}).get("symbol_code", ""))
                  for s in horizon]
    rainy = [t for t, c in rain_codes if _rainy(c)]
    if "chover" in q or "chuva" in q or "guarda chuva" in q:
        if rainy:
            return f"Sim, {sir}: deve chover em {city} a partir das {rainy[0]:%H:%M}."
        return f"Não há previsão de chuva nas próximas 12 horas em {city}, {sir}."
    if "amanha" in q:
        tomorrow = (datetime.now() + timedelta(days=1)).date()
        temps = [s["data"]["instant"]["details"]["air_temperature"] for s in series
                 if datetime.fromisoformat(s["time"].replace("Z", "+00:00")).astimezone().date() == tomorrow]
        if temps:
            return f"Amanhã em {city}: mínima de {min(temps):.0f}°C e máxima de {max(temps):.0f}°C, {sir}."
    extra = f", {_describe(code1)}" if code1 else ""
    rain = f" Deve chover a partir das {rainy[0]:%H:%M}." if rainy else ""
    return f"Agora em {city} faz {now:.0f}°C{extra}.{rain} {sir.capitalize()}."


# ---------------------------------------------------------------- opening apps (Start menu, UWP, aliases)

_apps_cache = {"t": 0, "list": []}


def installed_apps(force=False):
    """[(name, launch target)] from the Start menu shortcuts and the Store apps."""
    if not force and _apps_cache["list"] and time.time() - _apps_cache["t"] < 600:
        return _apps_cache["list"]
    apps = {}
    for root in (Path(os.environ.get("ProgramData", "")) / "Microsoft/Windows/Start Menu/Programs",
                 Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs"):
        if root.exists():
            for lnk in root.rglob("*.lnk"):
                name = lnk.stem
                if not re.search(r"unins|desinstal|uninstall|readme|leia-me", name, re.I):
                    apps.setdefault(name, str(lnk))
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ForEach-Object { $_.Name + '|' + $_.AppID }"],
                             capture_output=True, text=True, encoding="utf-8", timeout=25, creationflags=NOFLASH).stdout
        for line in out.splitlines():
            if "|" in line:
                name, appid = line.rsplit("|", 1)
                apps.setdefault(name.strip(), "shell:AppsFolder\\" + appid.strip())
    except Exception:
        pass
    _apps_cache.update(t=time.time(), list=sorted(apps.items()))
    return _apps_cache["list"]


_SECOND = ("segundo", "segunda", "2", "dois", "outro", "outra", "clone", "paralelo")


def find_app(spoken: str, aliases: dict):
    """Nicknames first ('whats 2'), then name matching. Returns (name, target) or None."""
    s = norm(spoken)
    for nick, name in aliases.items():
        if norm(nick) == s or (len(norm(nick)) > 2 and norm(nick) in s):
            for n, target in installed_apps():
                if n == name:
                    return n, target
    if s in ("whats", "zap", "whatsapp", "zap zap"):
        s = "whatsapp"
    scored = []
    for n, target in installed_apps():
        nn = norm(n)
        score = 100 if nn == s else 80 if nn.startswith(s) else 60 if s in nn else 40 if nn in s and len(nn) > 3 else 0
        if score:
            scored.append((score - len(nn) / 100, n, target))
    scored.sort(reverse=True)
    return (scored[0][1], scored[0][2]) if scored else None


def launch(target: str):
    if target.startswith("shell:"):
        subprocess.Popen(["explorer.exe", target], creationflags=NOFLASH)
    else:
        os.startfile(target)


def open_url(url: str):
    if not re.match(r"^https?://", url):
        url = "https://" + url
    os.startfile(url)


# ---------------------------------------------------------------- timers and alarms

_timers = []


def add_timer(seconds: int, label: str, on_fire):
    t = threading.Timer(max(1, seconds), on_fire, args=(label or "Timer",))
    t.daemon = True
    t.start()
    _timers.append(t)


def add_alarm(hour: int, minute: int, label: str, on_fire):
    now = datetime.now()
    target = now.replace(hour=hour % 24, minute=minute % 60, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    add_timer(int((target - now).total_seconds()), label or f"Alarme das {target:%H:%M}", on_fire)
    return target


# ---------------------------------------------------------------- calendar (Outlook on this computer)

def calendar_events(day_offset=0):
    """Today's (or tomorrow's) appointments from the classic Outlook app, if installed. Returns None if unavailable."""
    day = (datetime.now() + timedelta(days=day_offset)).date()
    script = ("$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.Encoding]::UTF8; "
              "$o=New-Object -ComObject Outlook.Application; $c=$o.GetNamespace('MAPI').GetDefaultFolder(9).Items; "
              "$c.IncludeRecurrences=$true; $c.Sort('[Start]'); "
              f"$s=[datetime]'{day:%Y-%m-%d}'; $e=$s.AddDays(1); "
              "$f=\"[Start] < '\"+$e.ToString('g')+\"' AND [End] > '\"+$s.ToString('g')+\"'\"; "
              "foreach($i in $c.Restrict($f)){ $i.Start.ToString('HH:mm') + '|' + $i.Subject }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True,
                             encoding="utf-8", timeout=30, creationflags=NOFLASH)
        if out.returncode != 0:
            return None
        return [tuple(line.split("|", 1)) for line in out.stdout.splitlines() if "|" in line]
    except Exception:
        return None


# ---------------------------------------------------------------------- monitors
def monitors():
    """The connected screens, numbered like Windows does (Settings > Display): [{n, rect=(l,t,r,b), primary, where}]."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32

    class INFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD), ("szDevice", ctypes.c_wchar * 32)]
    proc = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
    user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    found = []

    def cb(handle, dc, rect, lparam):
        info = INFO()
        info.cbSize = ctypes.sizeof(INFO)
        user32.GetMonitorInfoW(handle, ctypes.byref(info))
        m = re.search(r"DISPLAY(\d+)", info.szDevice)
        r = info.rcMonitor
        found.append({"n": int(m.group(1)) if m else 0, "rect": (r.left, r.top, r.right, r.bottom), "primary": bool(info.dwFlags & 1),
                      "key": f"{r.left},{r.top},{r.right - r.left},{r.bottom - r.top}"})
        return 1
    try:
        user32.EnumDisplayMonitors(None, None, proc(cb), 0)
    except Exception:
        return []
    if len({m["n"] for m in found}) != len(found) or 0 in {m["n"] for m in found}:  # no usable Windows numbers: left to right
        for i, m in enumerate(sorted(found, key=lambda m: (m["rect"][0], m["rect"][1])), 1):
            m["n"] = i
    found.sort(key=lambda m: m["n"])
    main = next((m for m in found if m["primary"]), found[0] if found else None)
    for m in found:
        l, t, r, b = m["rect"]
        if m is main:
            m["where"] = "principal"
        else:
            ml, mt, mr, mb = main["rect"]
            m["where"] = "à direita da principal" if l >= mr else "à esquerda da principal" if r <= ml else "acima da principal" if b <= mt else "abaixo da principal"
    return found


def cursor_monitor(mons):
    import ctypes
    from ctypes import wintypes
    pt = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    for m in mons:
        l, t, r, b = m["rect"]
        if l <= pt.x < r and t <= pt.y < b:
            return m
    return mons[0] if mons else None


def active_monitor(mons):
    """The monitor of the window the user is working in (the foreground window); the one with the mouse cursor when there is none."""
    import ctypes
    from ctypes import wintypes
    try:
        u = ctypes.windll.user32
        u.GetForegroundWindow.restype = ctypes.c_void_p
        u.MonitorFromWindow.restype = ctypes.c_void_p
        u.MonitorFromWindow.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        hwnd = u.GetForegroundWindow()
        if hwnd:
            rect = wintypes.RECT()
            u.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect))
            cx, cy = (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2
            for m in mons:
                l, t, r, b = m["rect"]
                if l <= cx < r and t <= cy < b:
                    return m
    except Exception:
        pass
    return cursor_monitor(mons)


_ORDINALS = {"primeir": 1, "segund": 2, "terceir": 3, "quart": 4, "quint": 5}
_NUMBERS = {"1": 1, "um": 1, "uma": 1, "2": 2, "dois": 2, "duas": 2, "3": 3, "tres": 3, "4": 4, "quatro": 4, "5": 5, "cinco": 5}
_SCREEN_WORDS = ("tela", "monitor", "video", "display", "ecra")


def _screen_word(w):
    import difflib
    return any(difflib.SequenceMatcher(None, w, s).ratio() >= 0.6 for s in _SCREEN_WORDS)


def parse_screen(text, names=None):
    """Which screen the user named in plain words: 2, "all" or "other"; None when he did not say. Tolerant to speech-recognition slips
    ("primeira hotel" for "primeira tela"). The numbers are the ones Windows shows in Settings > Display."""
    t = norm(text)
    for nick in sorted(names or {}, key=len, reverse=True):   # the nicknames he gave his screens ("notebook", "monitor grande") come first
        if nick and re.search(r"\b" + re.escape(nick) + r"\b", t):
            return names[nick]
    if re.search(r"\b(todas|todos|ambas|ambos)\b[^.]{0,12}\b(telas?|monitores|videos?)\b|\b(duas|dois|as 2|os 2)\b[^.]{0,6}\b(telas|monitores|videos)\b", t):
        return "all"
    for m in re.finditer(r"\b(primeir|segund|terceir|quart|quint)[oa]s?\s+(\w+)", t):
        if _screen_word(m.group(2)):
            return _ORDINALS[m.group(1)]
    m = re.search(r"\b(?:tela|monitor|video|display)s?\s*(?:numero\s*|n\s*|no\s*)?(\d|um|uma|dois|duas|tres|quatro|cinco)\b", t)
    if m:
        return _NUMBERS[m.group(1)]
    if re.search(r"\b(outra|outro)\s+(tela|monitor|video)\b", t):
        return "other"
    return None


def screens_note(nicks=None):
    """One line telling the model which screens exist and where the user is working; empty with a single screen."""
    mons = monitors()
    if len(mons) < 2:
        return ""
    cur = active_monitor(mons)
    nicks = nicks or {}
    parts = ", ".join((f"\"{nicks[m['n']]}\" (tela {m['n']}, " if nicks.get(m["n"]) else f"tela {m['n']} (") + f"{m['where']}, {m['rect'][2] - m['rect'][0]}x{m['rect'][3] - m['rect'][1]})" for m in mons)
    return f"Telas (numeração do Windows): {parts}; a janela ativa dele está em {(chr(34) + nicks[cur['n']] + chr(34)) if nicks.get(cur['n']) else 'tela ' + str(cur['n'])}" + ("; chame as telas pelo APELIDO, nunca pelo número" if nicks else "")


# ---------------------------------------------------------------------- screen capture and reading
def grab_rect(left, top, right, bottom):
    """A picture of that rectangle of the virtual desktop, taken straight from Windows (BitBlt) in the same pixel coordinates that
    monitors() reports, so the right monitor is always the one captured."""
    import ctypes
    from ctypes import wintypes
    from PIL import Image
    u, g = ctypes.windll.user32, ctypes.windll.gdi32
    vp = ctypes.c_void_p
    u.GetDC.restype, u.GetDC.argtypes = vp, [vp]
    u.ReleaseDC.argtypes = [vp, vp]
    g.CreateCompatibleDC.restype, g.CreateCompatibleDC.argtypes = vp, [vp]
    g.CreateCompatibleBitmap.restype, g.CreateCompatibleBitmap.argtypes = vp, [vp, ctypes.c_int, ctypes.c_int]
    g.SelectObject.restype, g.SelectObject.argtypes = vp, [vp, vp]
    g.BitBlt.argtypes = [vp, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, vp, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
    g.GetDIBits.argtypes = [vp, vp, ctypes.c_uint, ctypes.c_uint, vp, vp, ctypes.c_uint]
    g.DeleteObject.argtypes = [vp]
    g.DeleteDC.argtypes = [vp]
    w, h = int(right - left), int(bottom - top)
    if w <= 0 or h <= 0:
        raise ValueError("área vazia")

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                    ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                    ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]
    screen_dc = u.GetDC(None)
    mem = g.CreateCompatibleDC(screen_dc)
    bmp = g.CreateCompatibleBitmap(screen_dc, w, h)
    old = g.SelectObject(mem, bmp)
    try:
        if not g.BitBlt(mem, 0, 0, w, h, screen_dc, int(left), int(top), 0x00CC0020 | 0x40000000):   # SRCCOPY | CAPTUREBLT (layered windows too)
            raise OSError("BitBlt falhou")
        bih = BIH(ctypes.sizeof(BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)   # negative height: top-down rows
        buf = ctypes.create_string_buffer(w * h * 4)
        if not g.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bih), 0):
            raise OSError("GetDIBits falhou")
        return Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1).copy()
    finally:
        g.SelectObject(mem, old)
        g.DeleteObject(bmp)
        g.DeleteDC(mem)
        u.ReleaseDC(None, screen_dc)


_OCR_PS = r"""param([string]$Path)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) { $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bmp = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($null -eq $engine) { exit 2 }
$result = Await ($engine.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
[Console]::OutputEncoding = [Text.Encoding]::UTF8
"# idioma: " + $engine.RecognizerLanguage.LanguageTag
$result.Lines | ForEach-Object { $_.Text }
"""


def ocr_image(path, scale=2):
    """The text on a picture, read offline by Windows' own OCR (the languages installed for the user, e.g. Portuguese and English).
    Small text reads much better when the picture is enlarged first. Returns "" if nothing could be read."""
    import subprocess, tempfile, uuid
    from PIL import Image
    from .store import ROOT
    src, tmp = Path(path), None
    try:
        im = Image.open(src)
        if scale > 1 and im.width * scale <= 6000 and im.height * scale <= 6000:
            tmp = Path(tempfile.gettempdir()) / f"gota_ocr_{uuid.uuid4().hex[:8]}.png"   # unique: several pictures are read at the same time
            im.convert("RGB").resize((im.width * scale, im.height * scale), Image.LANCZOS).save(tmp)
            src = tmp
        script = ROOT / "ocr.ps1"
        if not script.exists() or script.read_text("utf-8-sig") != _OCR_PS:
            script.write_text(_OCR_PS, "utf-8-sig")
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Path", str(src)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, creationflags=0x08000000)
        return "\n".join(l for l in r.stdout.splitlines() if l.strip() and not l.startswith("# idioma"))
    except Exception:
        return ""
    finally:
        if tmp is not None:
            try:
                tmp.unlink()
            except OSError:
                pass


def ocr_tiles(path, cols=3, rows=2, scale=3, overlap=0.06):
    """OCR of a whole screen read in tiles, each enlarged: small text (the lines of a log panel, a job list) that a single pass over the whole screen misreads or
    skips comes out readable. The tiles are read at the same time. Returns the text in reading order (top-left to bottom-right), repeated lines dropped."""
    import tempfile, uuid
    from concurrent.futures import ThreadPoolExecutor
    from PIL import Image
    im = Image.open(path).convert("RGB")
    if im.width < 900 or im.height < 500:
        return ocr_image(path, scale)
    w, h = im.width // cols, im.height // rows
    boxes = [(max(0, int(c * w - overlap * w)), max(0, int(r * h - overlap * h)), min(im.width, int((c + 1) * w + overlap * w)), min(im.height, int((r + 1) * h + overlap * h)))
             for r in range(rows) for c in range(cols)]

    def read(box):
        tile = Path(tempfile.gettempdir()) / f"gota_tile_{uuid.uuid4().hex[:8]}.png"
        try:
            im.crop(box).save(tile)
            return ocr_image(tile, scale)
        finally:
            try:
                tile.unlink()
            except OSError:
                pass
    with ThreadPoolExecutor(max_workers=len(boxes)) as pool:
        texts = list(pool.map(read, boxes))
    seen, out = set(), []
    for text in texts:
        for line in text.splitlines():
            key = re.sub(r"\W+", "", line.lower())
            if line.strip() and key not in seen:
                seen.add(key)
                out.append(line.strip())
    return "\n".join(out)


# strong = what names a cause; weak = a summary that only says "something failed" (the cause is on the lines above it); NEGATED = reassurance, not a problem
STRONG = re.compile(r"(error:|\berror\b|erro\b|failed|falha|exception|object reference|reference not set|not set to an instance|instance of an|cannot|can't|unable|denied|negado|timeout|timed out|aborted|abortad|corrupt(?!ed blocks)|"
                    r"n[aã]o foi poss[ií]vel|critical|cr[ií]tico|0x[0-9a-f]{4,8}|event id|unreachable|refused|disconnected|terminated|invalid|missing|not found)", re.I)
WEAK = re.compile(r"(finished with (err|warn)|completed with (err|warn)|warning|aviso)", re.I)
NEGATED = re.compile(r"\b(no|zero|0|sem|nenhum)\s+(corrupt\w*|errors?|erros?|failures?|warnings?)\b|detected no |success", re.I)


def problem_lines(text, limit=8):
    """The lines of an on-screen text that name an error: causes first (in screen order), then the summaries that only say it finished with errors.
    Lines that say everything is fine ("no corrupted blocks") are left out."""
    seen, strong, weak = set(), [], []
    for line in text.splitlines():
        line = line.strip()
        if len(line) < 15 or line.lower() in seen or NEGATED.search(line):
            continue
        if STRONG.search(line):
            seen.add(line.lower())
            strong.append(line)
        elif WEAK.search(line):
            seen.add(line.lower())
            weak.append(line)
    return (strong + weak)[:limit]


def selected_row_crop(image_path, max_width=820, scale=3):
    """A magnified picture of the highlighted (selected) row of a list on screen (its first `max_width` pixels, enlarged `scale` times), saved as a
    file; None when no highlighted row is found (only the light-blue Windows selection is recognised). The vision model reads names such as
    JOB_BACKUP_TAPE_NOD01_B from it exactly, which it cannot do from the whole screen."""
    try:
        import tempfile
        import numpy as np
        from PIL import Image
        im = Image.open(image_path).convert("RGB")
        a = np.asarray(im).astype(int)
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        mask = (abs(r - 205) < 28) & (abs(g - 232) < 22) & (b > 232)
        rows = np.where(mask.mean(axis=1) > 0.4)[0]
        if not len(rows):
            return None
        bands, start = [], rows[0]
        for prev, cur in zip(rows, list(rows[1:]) + [None]):
            if cur is None or cur - prev > 2:
                bands.append((start, prev))
                start = cur
        bands = [bd for bd in bands if 8 <= bd[1] - bd[0] + 1 <= 70]
        if not bands:
            return None
        top, bottom = min(bands)   # the highest highlighted row: the selected job/item of the list (a log line selected further down is not what the job is called)
        cols = np.where(mask[top:bottom + 1].mean(axis=0) > 0.5)[0]
        left = int(cols[0]) if len(cols) else 0
        crop = im.crop((left, max(0, top - 3), min(im.width, left + max_width), min(im.height, bottom + 4)))
        crop = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
        path = Path(tempfile.gettempdir()) / "gota_selected_row.png"
        crop.save(path)
        return path
    except Exception:
        return None
