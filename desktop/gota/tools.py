"""What Gota can do on the computer: search the web, weather, open apps, timers and the calendar."""
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


def is_online() -> bool:
    try:
        http("https://www.bing.com/robots.txt", timeout=4, limit=200)
        return True
    except Exception:
        return False


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
