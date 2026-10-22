"""Instant answers that need no model at all: arithmetic, percentages, roots, powers and unit conversions.
Everything here is exact (done by the computer, not guessed by a language model) and answers in a blink."""
import ast, math, operator, re, unicodedata

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos, ast.Mod: operator.mod}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        a, b = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and (abs(b) > 100 or abs(a) > 1e9):
            raise ValueError("too big")
        return OPS[type(node.op)](a, b)
    if isinstance(node, ast.UnaryOp) and type(node.op) in OPS:
        return OPS[type(node.op)](_eval(node.operand))
    raise ValueError("not arithmetic")


def fmt(x):
    """12345.5 -> '12.345,5' (Brazilian style), no useless decimals."""
    if isinstance(x, float) and x.is_integer() and abs(x) < 1e15:
        x = int(x)
    if isinstance(x, int):
        return f"{x:,}".replace(",", ".")
    s = f"{x:,.6f}".rstrip("0").rstrip(".")
    whole, _, frac = s.partition(".")
    return whole.replace(",", ".") + ("," + frac if frac else "")


def _num(s):
    """'1.234,5' or '1234.5' or '3,5' -> float."""
    s = s.strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1 or re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    return float(s)


NUM = r"\d+(?:[.,]\d+)*"
ASK = r"^(?:por favor\s+)?(?:(?:me\s+)?(?:diz|diga|fala|fale)\s+)?(?:quanto\s+(?:e|eh|da|fica|vale|seria)|qual\s+(?:e\s+)?(?:o\s+)?(?:resultado|valor)\s+(?:de|da)|calcule|calcula|calcular|resultado\s+de|conta)\s+"


def percent(t):
    m = re.match(ASK + r"(?:de\s+)?(" + NUM + r")\s*(?:%|por\s*cento)\s+(?:de|do|da)\s+(" + NUM + r")\s*\??$", t) or re.match(r"^(" + NUM + r")\s*(?:%|por\s*cento)\s+(?:de|do|da)\s+(" + NUM + r")\s*\??$", t)
    if not m:
        return None
    p, base = _num(m.group(1)), _num(m.group(2))
    return f"{fmt(p)}% de {fmt(base)} é {fmt(round(p * base / 100, 6))}"


def arithmetic(t):
    m = re.match(ASK + r"(.+?)\??$", t)
    body = m.group(1) if m else (t.rstrip("?") if re.fullmatch(r"[\d\s.,+\-*/x×÷^()]+", t.rstrip("?")) and re.search(r"\d\s*[+\-*/x×÷^]\s*\d", t) else None)
    if not body:
        return None
    if re.search(r"\braiz\b", body) or re.search(r"ao\s+(quadrado|cubo)", body):
        r = re.fullmatch(r"(?:a\s+)?raiz\s+(quadrada|cubica)\s+de\s+(" + NUM + r")", body)
        if r:
            n = _num(r.group(2))
            if r.group(1) == "quadrada" and n >= 0:
                return f"A raiz quadrada de {fmt(n)} é {fmt(round(math.sqrt(n), 6))}"
            if r.group(1) == "cubica":
                return f"A raiz cúbica de {fmt(n)} é {fmt(round(math.copysign(abs(n) ** (1 / 3), n), 6))}"
        r = re.fullmatch(r"(" + NUM + r")\s+ao\s+(quadrado|cubo)", body)
        if r:
            n = _num(r.group(1))
            return f"{fmt(n)} ao {r.group(2)} é {fmt(round(n ** (2 if r.group(2) == 'quadrado' else 3), 6))}"
        return None
    e = body
    for words, op in ((r"elevado\s+a(?:\s+potencia)?", "**"), (r"multiplicado\s+por", "*"), (r"dividido\s+por", "/"), (r"vezes", "*"), (r"mais", "+"), (r"menos", "-"), (r"sobre", "/"), (r"resto\s+de", "%")):
        e = re.sub(r"\b" + words + r"\b", f" {op} ", e)
    e = e.replace("×", "*").replace("÷", "/").replace("^", "**")
    e = re.sub(r"(?<=\d)\s*x\s*(?=\d)", " * ", e)
    e = re.sub(r"\s+", " ", e).strip()
    if not re.fullmatch(r"[\d\s.,+\-*/()%]+", e) or len(re.findall(NUM, e)) < 2 or not re.search(r"[+\-*/%]", e):
        return None
    e = re.sub(NUM, lambda m: str(_num(m.group(0))), e)
    try:
        value = _eval(ast.parse(e, mode="eval"))
    except (ValueError, SyntaxError, ZeroDivisionError, OverflowError, RecursionError):
        return None
    pretty = re.sub(r"\s+", " ", body).strip()
    return f"{pretty} = {fmt(round(value, 6))}"


# ---------------------------------------------------------------------- units
LENGTH = {"km": 1000, "quilometro": 1000, "quilometros": 1000, "m": 1, "metro": 1, "metros": 1, "cm": .01, "centimetro": .01, "centimetros": .01, "mm": .001, "milimetro": .001, "milimetros": .001,
          "milha": 1609.344, "milhas": 1609.344, "pe": .3048, "pes": .3048, "polegada": .0254, "polegadas": .0254, "jarda": .9144, "jardas": .9144}
MASS = {"kg": 1000, "quilo": 1000, "quilos": 1000, "quilograma": 1000, "quilogramas": 1000, "g": 1, "grama": 1, "gramas": 1, "mg": .001, "t": 1e6, "tonelada": 1e6, "toneladas": 1e6,
        "lb": 453.59237, "libra": 453.59237, "libras": 453.59237, "oz": 28.349523, "onca": 28.349523, "oncas": 28.349523}
VOLUME = {"l": 1, "litro": 1, "litros": 1, "ml": .001, "mililitro": .001, "mililitros": .001, "galao": 3.785411784, "galoes": 3.785411784}
STORAGE = {"b": 1, "byte": 1, "bytes": 1, "kb": 1024, "mb": 1024 ** 2, "gb": 1024 ** 3, "tb": 1024 ** 4, "pb": 1024 ** 5}
TIME = {"s": 1, "seg": 1, "segundo": 1, "segundos": 1, "min": 60, "minuto": 60, "minutos": 60, "h": 3600, "hora": 3600, "horas": 3600, "dia": 86400, "dias": 86400, "semana": 604800, "semanas": 604800}
TEMP = {"c": "c", "celsius": "c", "f": "f", "fahrenheit": "f", "k": "k", "kelvin": "k"}
NAMES = {"quilometro": "km", "quilometros": "km", "metro": "m", "metros": "m", "milha": "milhas", "pe": "pés", "pes": "pés", "libra": "libras", "quilo": "kg", "quilos": "kg", "litro": "litros", "litros": "litros"}


def _table(u):
    for name, tab in (("length", LENGTH), ("mass", MASS), ("volume", VOLUME), ("storage", STORAGE), ("time", TIME)):
        if u in tab:
            return name, tab
    return None, None


def convert(t):
    m = re.match(r"^(?:por favor\s+)?(?:(?:me\s+)?(?:diz|diga)\s+)?(?:quanto\s+(?:e|eh|vale|da|fica|seria)|quantos?|quantas?|converta|converte|converter|transforme|transforma)?\s*(" + NUM + r")\s*(?:graus?\s+)?([a-z]+)\s+(?:em|para|pra)\s+(?:graus?\s+)?([a-z]+)\s*\??$", t)
    if not m:
        return None
    n, a, b = _num(m.group(1)), m.group(2), m.group(3)
    if a in TEMP and b in TEMP:
        ua, ub = TEMP[a], TEMP[b]
        c = n if ua == "c" else (n - 32) * 5 / 9 if ua == "f" else n - 273.15
        out = c if ub == "c" else c * 9 / 5 + 32 if ub == "f" else c + 273.15
        sym = {"c": "°C", "f": "°F", "k": " K"}
        return f"{fmt(n)}{sym[ua]} equivalem a {fmt(round(out, 2))}{sym[ub]}"
    ka, ta = _table(a)
    kb, tb = _table(b)
    if not ka or ka != kb:
        return None
    value = n * ta[a] / tb[b]
    note = " (considerando 1 GB = 1024 MB)" if ka == "storage" else ""
    return f"{fmt(n)} {NAMES.get(a, a)} equivalem a {fmt(round(value, 6))} {NAMES.get(b, b)}{note}"


def prep(text):
    """Lower case, no accents, but keeps the symbols a calculation needs (% , . + - * / ( ) ^)."""
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"\s+", " ", t).strip()
    return t.rstrip("!.")


def answer(text):
    """The instant answer for a sentence as the user wrote it, or None when it is not a plain calculation or conversion."""
    t = prep(text)
    return percent(t) or convert(t) or arithmetic(t)
