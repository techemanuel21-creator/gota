"""Draws pictures on this computer, offline, with the same SDXS-512 DreamShaper model as the phone app."""
import json, re, threading, time, urllib.request
from pathlib import Path
from .store import MODELS, ROOT

REPO = "https://huggingface.co/software-mansion/react-native-executorch-sdxs-512-dreamshaper/resolve/main/"
TOK_REPO = "https://huggingface.co/IDKiro/sdxs-512-dreamshaper/resolve/main/tokenizer/"
DIR = MODELS / "imagegen"
PTE = DIR / "sdxs_cpu.pte"
PTE_URL = REPO + "xnnpack/sdxs_512_dreamshaper_xnnpack_fp32.pte"
PTE_MB = 1679
def _pictures():
    """The profile's Pictures folder as Windows knows it (it may be redirected, e.g. to OneDrive)."""
    try:
        import ctypes, uuid
        from ctypes import wintypes
        guid = uuid.UUID("{33E28130-4E1E-4676-835A-98395C3BC3BB}")  # FOLDERID_Pictures
        raw_guid = (ctypes.c_byte * 16).from_buffer_copy(guid.bytes_le)
        out = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(raw_guid), 0, None, ctypes.byref(out)) == 0:
            path = Path(out.value)
            ctypes.windll.ole32.CoTaskMemFree(out)
            return path
    except Exception:
        pass
    return Path.home() / "Pictures"


ALBUM = _pictures() / "GOTA AI"   # created on first use
TIMESTEP, A, B = 999, 14.642591, -14.579279  # the single-step scheduler as a linear mix

PAINTERLY = re.compile(r"\b(oil painting|painting|watercolou?r|impressionis\w*|brush ?strokes?|gouache|acrylic)\b")
STYLED = re.compile(r"\b(cartoon|anime|manga|comic|illustration|drawing|sketch|pixel art|vector|3d render|render|digital art|logo|icon|flat design|clay|lego|isometric|low poly|cel.?shaded)\b")
PHOTO = "RAW photo, sharp focus, highly detailed, natural lighting, realistic textures, 8k uhd"
ART = "clean crisp lines, highly detailed, sharp focus, smooth shading, high quality"
PAINTING = "highly detailed, beautiful, masterpiece, high quality"


def suffix_for(prompt):
    p = prompt.lower()
    return PAINTING if PAINTERLY.search(p) else ART if STYLED.search(p) else PHOTO


class NotReady(Exception):
    pass


def _asset(name):
    """A file that ships with the models (the full-quality image decoder lives next to the painter)."""
    return DIR / name


class ClipTokenizer:
    """The CLIP byte-pair tokenizer of Stable Diffusion (identical to the phone app's)."""
    START, END, MAX = 49406, 49407, 77
    PATTERN = re.compile(r"<\|startoftext\|>|<\|endoftext\|>|'s|'t|'re|'ve|'m|'ll|'d|[^\W\d_]+|\d|[^\s\w]+", re.I)

    def __init__(self, vocab_json, merges_txt):
        self.vocab = json.loads(vocab_json)
        lines = [l for l in merges_txt.splitlines() if l.strip() and not l.startswith("#version")][:49152 - 256 - 2]
        self.ranks = {l: i for i, l in enumerate(lines)}
        bs = list(range(33, 127)) + list(range(161, 173)) + list(range(174, 256))
        cs, n = bs[:], 0
        for b in range(256):
            if b not in bs:
                bs.append(b); cs.append(256 + n); n += 1
        self.b2c = dict(zip(bs, map(chr, cs)))
        self.cache = {}

    def _bpe(self, token):
        if token in self.cache:
            return self.cache[token]
        word = list(token[:-1]) + [token[-1] + "</w>"]
        while len(word) > 1:
            best, rank = -1, 1 << 30
            for i in range(len(word) - 1):
                r = self.ranks.get(f"{word[i]} {word[i + 1]}")
                if r is not None and r < rank:
                    best, rank = i, r
            if best == -1:
                break
            a, b = word[best], word[best + 1]
            out, i = [], 0
            while i < len(word):
                if i < len(word) - 1 and word[i] == a and word[i + 1] == b:
                    out.append(a + b); i += 2
                else:
                    out.append(word[i]); i += 1
            word = out
        self.cache[token] = word
        return word

    def tokens(self, text):
        ids = []
        for m in self.PATTERN.finditer(re.sub(r"\s+", " ", text).strip().lower()):
            mapped = "".join(self.b2c[b] for b in m.group().encode("utf-8"))
            ids += [self.vocab[p] for p in self._bpe(mapped) if p in self.vocab]
        return ids

    def encode(self, text, suffix=""):
        tail = self.tokens(suffix) if suffix else []
        ids = self.tokens(text)[:max(0, self.MAX - 2 - len(tail))] + tail
        ids = ids[:self.MAX - 2]
        return [self.START] + ids + [self.END] * (self.MAX - 1 - len(ids))


def _download(url, dest: Path, progress):
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0
    headers = {"User-Agent": "GotaDesktop/1.0"}
    if have:
        headers["Range"] = f"bytes={have}-"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
        resumed = r.status == 206
        done = have if resumed else 0
        total = done + int(r.headers.get("Content-Length", 0))
        with open(part, "ab" if resumed else "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk); done += len(chunk)
                if total:
                    progress(int(done * 100 / total))
    part.replace(dest)


class ImageGen:
    NotReady = NotReady

    def __init__(self):
        self.lock = threading.Lock()
        self.downloading = False
        self.percent = 0
        self.tok = None
        self.program = None

    def ready(self):
        return PTE.exists() and (DIR / "vocab.json").exists() and (DIR / "merges.txt").exists()

    def start_download(self, on_done=lambda ok: None):
        if self.downloading or self.ready():
            return
        self.downloading = True

        def work():
            ok = False
            try:
                for name in ("vocab.json", "merges.txt"):
                    if not (DIR / name).exists():
                        _download(TOK_REPO + name, DIR / name, lambda p: None)
                _download(PTE_URL, PTE, lambda p: setattr(self, "percent", p))
                ok = True
            except Exception:
                pass
            self.downloading = False
            on_done(ok)
        threading.Thread(target=work, daemon=True).start()

    def _decode_full(self, latents):
        """The full Stable Diffusion image decoder (cleaner edges and eyes than the tiny one built into the painter)."""
        vae = _asset("vae_decoder_fp32.pte")
        if not vae.exists():
            return None
        try:
            from executorch.runtime import Runtime
            if getattr(self, "vae_method", None) is None:
                self.vae_method = Runtime.get().load_program(str(vae)).load_method("forward")
            return self.vae_method.execute([latents])[0][0].clamp(0, 1)
        except Exception:
            return None

    def generate(self, prompt, on_status=lambda s: None) -> Path:
        if not self.ready():
            if self.downloading:
                raise NotReady(f"Ainda estou baixando meu pintor ({self.percent}% de {PTE_MB} MB). Quando terminar, é só pedir de novo.")
            self.start_download()
            raise NotReady(f"Preciso baixar meu pintor uma única vez ({PTE_MB} MB). Já comecei; aviso quando terminar.")
        with self.lock:
            import numpy as np, torch
            from PIL import Image, ImageFilter
            from executorch.runtime import Runtime
            if self.tok is None:
                self.tok = ClipTokenizer((DIR / "vocab.json").read_text("utf-8"), (DIR / "merges.txt").read_text("utf-8"))
            if self.program is None:
                self.program = Runtime.get().load_program(str(PTE))
            on_status("Imaginando a cena...")
            ids = torch.tensor([self.tok.encode(prompt, suffix_for(prompt))], dtype=torch.int64)
            emb = self.program.load_method("encode").execute([ids])[0]
            x = torch.randn(1, 4, 64, 64)
            eps = self.program.load_method("denoise").execute([x, torch.tensor([TIMESTEP], dtype=torch.int64), emb])[0]
            on_status("Terminando a imagem...")
            latents = A * x + B * eps
            rgb = self._decode_full(latents)
            if rgb is None:
                rgb = self.program.load_method("decode").execute([latents])[0][0].clamp(0, 1)
            arr = (rgb.permute(1, 2, 0).numpy() * 255 + 0.5).astype(np.uint8)
            img = Image.fromarray(arr).resize((1024, 1024), Image.BICUBIC).filter(ImageFilter.UnsharpMask(radius=1.6, percent=80, threshold=2))
            ALBUM.mkdir(parents=True, exist_ok=True)
            path = ALBUM / f"gota_{int(time.time())}.jpg"
            img.save(path, quality=93)
            return path
