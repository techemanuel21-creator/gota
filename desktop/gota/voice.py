"""Voice: a deep, unhurried butler voice (Windows SAPI), offline speech recognition (Vosk) and a global hotkey."""
import ctypes, io, json, queue, threading, time, urllib.request, zipfile
from ctypes import wintypes
from pathlib import Path
from .store import MODELS, ROOT

VOSK_URL = "https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip"
VOSK_DIR = MODELS / "vosk-pt"
WAKE_GRAMMAR = json.dumps(["ei gota", "oi gota", "hey gota", "gota", "[unk]"])
MALE_HINTS = ("daniel", "antonio", "helio", "ricardo", "felipe", "male")


def xml_escape(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx"
PIPER_DIR = MODELS / "piper"


def ensure_piper_voice():
    """The male Brazilian voice 'faber' (Piper, MIT, ~63 MB), fetched once. Returns the model path or None."""
    model = PIPER_DIR / "pt_BR-faber-medium.onnx"
    try:
        PIPER_DIR.mkdir(parents=True, exist_ok=True)
        for url, dest in ((PIPER_BASE, model), (PIPER_BASE + ".json", Path(str(model) + ".json"))):
            if not dest.exists():
                tmp = Path(str(dest) + ".part")
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "GotaDesktop/1.0"}), timeout=60) as r, open(tmp, "wb") as f:
                    while chunk := r.read(1 << 20):
                        f.write(chunk)
                tmp.replace(dest)
        return model
    except Exception:
        return None


_EN_FUNCTION = set("the and is are was were to of in that it for with on this you be at by from has have had been not but or an will would could should can may if then than "
                   "when while which who what where how all any some your our their its his her they we please there here these those into about after before over under "
                   "between because during without within also only just very more most such other another each every both few many much own same".split())
_EN_IT = set("job backup server error errors failed failure fail success warning status result results last first next run running stopped started start stop complete completed "
             "processing process processed terminated termination aborted abort due connection connect connected disconnected timeout timed out access denied permission file files "
             "folder folders path network disk storage repository restore recovery snapshot virtual machine host cluster service services event log logs user password account "
             "login logout invalid unable cannot found missing data source target proxy bottleneck load primary finished read transferred duration rate speed size type name "
             "objects object scheduled schedule description action waiting resources infrastructure availability backed up created deleted updated retry details summary".split())
_EN_WORDS = _EN_FUNCTION | _EN_IT
_PT_WORDS = set("o a os as um uma uns umas de da do das dos em no na nos nas para por com sem que e é são não se mas ou ao à aos quando como mais muito já foi era ser "
                "está estão tem têm vai vou meu minha seu sua isso isto esse essa este esta aqui lá mesmo também então senhor senhora erro falha causa servidor tela "
                "ele ela eles elas eu você vocês nós me te lhe nem pois porque sobre entre até depois antes ainda sempre nunca só sim ter fazer pode podem deve".split())


def split_languages(text):
    """[(lang, text)] with lang 'en' for runs of three or more consecutive English words (function words and common IT/UI words, e.g. an error message
    or a label quoted from the screen, with no Portuguese word in between) and 'pt' for everything else."""
    import re
    tokens = re.findall(r"\s+|[^\s]+", text)
    kinds = []
    for tok in tokens:
        word = re.sub(r"[^\wÀ-ÿ']", "", tok).lower()
        if tok.isspace():
            kinds.append("space")
        elif re.search(r"[À-ÿ_\d]", tok) or word in _PT_WORDS:
            kinds.append("pt")
        elif word.isascii() and word in _EN_WORDS:
            kinds.append("en")
        else:
            kinds.append("pt")
    out, i = [], 0
    while i < len(tokens):
        if kinds[i] == "en":
            j, last = i, i
            while j < len(tokens) and kinds[j] in ("en", "space"):
                if kinds[j] == "en":
                    last = j
                j += 1
            words = sum(1 for k in range(i, last + 1) if kinds[k] == "en")
            if words >= 3:
                out.append(("en", "".join(tokens[i:last + 1])))
                i = last + 1
                continue
        out.append(("pt", tokens[i]))
        i += 1
    merged = []
    for lang, s in out:
        if merged and merged[-1][0] == lang:
            merged[-1] = (lang, merged[-1][1] + s)
        else:
            merged.append((lang, s))
    return [(l, s) for l, s in merged if s.strip()]


def spoken_form(text):
    """Makes names that are not words readable: JOB_BACKUP_TAPE_NOD01_B -> "job backup tape nod zero um bê" (parts split at _ and at letters/digits, digits one by one when
    they start with 0 or are short, single letters by their Portuguese name)."""
    import re
    letters = {c: n for c, n in zip("abcdefghijklmnopqrstuvwxyz", "á bê cê dê é éfe gê agá i jota cá éle ême ene ó pê quê érre ésse tê u vê dáblio xis ípsilon zê".split())}
    digits = "zero um dois três quatro cinco seis sete oito nove".split()

    def part(p):
        out = []
        for chunk in re.findall(r"[A-Za-z]+|\d+", p):
            if chunk.isdigit():
                out.append(" ".join(digits[int(d)] for d in chunk) if (chunk.startswith("0") or len(chunk) <= 2) else chunk)
            elif len(chunk) == 1:
                out.append(letters[chunk.lower()])
            else:
                out.append(chunk.lower())
        return " ".join(out)

    def ident(m):
        return ", ".join(part(p) for p in m.group(0).split("_") if p)
    return re.sub(r"\b[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+\b", ident, text)


EN_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/joe/medium/en_US-joe-medium.onnx"   # native US English, male, CC0 (public domain)
EN_PITCH = 164.0    # median pitch (Hz) of the Gota voice 'faber', measured; the English voice is moved to it
EN_FORMANT = 1.10   # vocal-tract shift that brings the English voice's formants closest to faber's (measured)


def ensure_english_voice(download=True):
    """The English voice 'joe' (Piper, CC0, ~63 MB) that reads English phrases with a native pronunciation. Returns the model path or None (not here yet)."""
    model = PIPER_DIR / "en_US-joe-medium.onnx"
    if model.exists() and Path(str(model) + ".json").exists():
        return model
    if not download:
        return None
    try:
        PIPER_DIR.mkdir(parents=True, exist_ok=True)
        for url, dest in ((EN_BASE, model), (EN_BASE + ".json", Path(str(model) + ".json"))):
            if not dest.exists():
                tmp = Path(str(dest) + ".part")
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "GotaDesktop/1.0"}), timeout=60) as r, open(tmp, "wb") as f:
                    while chunk := r.read(1 << 20):
                        f.write(chunk)
                tmp.replace(dest)
        return model
    except Exception:
        return None


def match_voice(samples, rate):
    """Moves a voice to the pitch and vocal-tract size of the Gota voice (Praat "Change gender"), so the English sounds like the same speaker."""
    import numpy as np
    import parselmouth
    from parselmouth.praat import call
    snd = parselmouth.Sound(np.asarray(samples, dtype=np.float64), sampling_frequency=rate)
    out = call(snd, "Change gender", 60, 300, EN_FORMANT, EN_PITCH, 1.0, 1.0)
    return np.asarray(out.values[0], dtype=np.float64)


class Speaker:
    """A classic butler's voice: male Piper voice, unhurried. Falls back to Windows' own voice if Piper is unavailable."""

    def __init__(self):
        self.q = queue.Queue()
        self.male = False
        self.ready = threading.Event()
        self.generation = 0
        threading.Thread(target=self._run, daemon=True).start()

    def _load_piper(self):
        try:
            model = ensure_piper_voice()
            if not model:
                return None
            from piper import PiperVoice
            from piper.config import SynthesisConfig
            self.cfg = SynthesisConfig(length_scale=1.12)  # slower = more dignified
            return PiperVoice.load(str(model))
        except Exception:
            return None

    def _load_sapi(self):
        import pyttsx3
        engine = pyttsx3.init()
        voices = [v for v in engine.getProperty("voices") if "pt" in "".join(v.languages).lower() or "portug" in v.name.lower()]
        if voices:
            engine.setProperty("voice", voices[0].id)
        engine.setProperty("rate", 150)
        return engine

    # the voice swallows the Portuguese "lh" (detalhadas -> detaadas, filho -> fio); "l" + "i" is pronounced reliably
    PT_FIX = {"ʎ": ["l", "i"]}

    def _synth_english(self, text, np):
        """Native English (the 'joe' voice) moved to the pitch and timbre of the Gota voice."""
        from piper.config import SynthesisConfig
        chunks = []
        for c in self.en_voice.synthesize(text, syn_config=SynthesisConfig(length_scale=1.12)):
            x = np.frombuffer(c.audio_int16_bytes, dtype=np.int16).astype(np.float64) / 32768.0
            try:
                x = match_voice(x, self.en_voice.config.sample_rate)
            except Exception:
                pass
            peak = float(np.max(np.abs(x))) if x.size else 0.0
            chunks.append((np.clip(x / peak if peak > 1e-8 else x, -1.0, 1.0) * 32767).astype(np.int16))
        return np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.int16)

    def _synth(self, piper, text, lang, np):
        """Speech for one piece: English by the English voice (or, until it is installed, by the Portuguese voice with English sounds);
        Portuguese through espeak phonemes with the sound fixes."""
        if lang == "en" and getattr(self, "en_voice", None) is not None:
            return self._synth_english(text, np)
        chunks = []
        for phonemes in piper.phonemize(text):
            if not phonemes:
                continue
            if lang != "en":
                phonemes = [q for p in phonemes for q in self.PT_FIX.get(p, [p])]
            audio = np.asarray(piper.phoneme_ids_to_audio(piper.phonemes_to_ids(phonemes), self.cfg), dtype=np.float32)
            peak = float(np.max(np.abs(audio))) if audio.size else 0.0
            audio = audio / peak if peak > 1e-8 else np.zeros_like(audio)
            chunks.append((np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16))
        return np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.int16)

    english = True   # read English phrases with English sounds (the same voice); can be switched off in the Voz e microfone window

    def _render(self, piper, text, np):
        """The audio for `text` in the SAME voice: English phrases are phonemized as English (espeak en-us) and spoken by the Portuguese voice, whose
        phoneme set covers them. A short pause separates them from the Portuguese around them."""
        text = spoken_form(text)
        pieces = split_languages(text) if self.english else [("pt", text)]
        pause = np.zeros(int(piper.config.sample_rate * 0.18), dtype=np.int16)
        parts = []
        for k, (lang, piece) in enumerate(pieces):
            old = piper.config.espeak_voice
            if lang == "en":
                piper.config.espeak_voice = "en-us"
            try:
                x = self._synth(piper, piece, lang, np)
            finally:
                piper.config.espeak_voice = old
            if lang == "en" and parts:
                parts.append(pause)
            parts.append(x)
            if lang == "en" and k < len(pieces) - 1:
                parts.append(pause)
        return np.concatenate(parts) if parts else np.zeros(1, dtype=np.int16)

    def _run(self):
        import numpy as np, sounddevice as sd
        piper = self._load_piper()
        sapi = None if piper else self._load_sapi()
        self.male = piper is not None
        self.en_voice = None
        if piper:   # the English voice is fetched in the background; until it is here English is spoken by the Portuguese voice with English sounds
            def load_en():
                try:
                    from piper import PiperVoice
                    model = ensure_english_voice()
                    if model:
                        self.en_voice = PiperVoice.load(str(model))
                except Exception:
                    pass
            threading.Thread(target=load_en, daemon=True).start()
        self.ready.set()
        while True:
            text, done, gen = self.q.get()
            try:
                if gen != self.generation or not text:   # an empty line only marks 'everything before me has been played'
                    continue
                if piper:
                    audio = self._render(piper, text, np)
                    if gen == self.generation:
                        sd.play(audio, piper.config.sample_rate)
                        while sd.get_stream().active and gen == self.generation:
                            time.sleep(0.05)
                        sd.stop()
                else:
                    sapi.say(f'<pitch absmiddle="-8">{xml_escape(text)}</pitch>')
                    sapi.runAndWait()
            except Exception:
                pass
            finally:
                if done and gen == self.generation:
                    try:
                        done()
                    except Exception:
                        pass

    def speak(self, text, done=None):
        import re
        clean = re.sub(r"```.*?(```|\Z)", " (o comando está no chat) ", text, flags=re.S)   # code is never read aloud
        clean = re.sub(r"[*_#`>]", "", clean)
        clean = re.sub(r"[𐀀-􏿿☀-➿]", "", clean).strip()
        if not clean:
            if done:
                done()
            return
        self.q.put((clean, done, self.generation))

    def after(self, done):
        """Calls done() once everything queued so far has been spoken."""
        self.q.put(("", done, self.generation))

    def stop(self):
        """Cuts the speech short: pending lines are dropped and the one playing is silenced."""
        self.generation += 1
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass
        try:
            self.sapi_stop()
        except Exception:
            pass

    def sapi_stop(self):
        pass


def speakable(text):
    """What is worth reading aloud: code blocks become one short remark. Stable while the text grows (the old part never changes)."""
    import re
    marker = " (o comando está no chat) "
    s = re.sub(r"```.*?```", marker, text, flags=re.S)
    cut = s.find("```")   # a block that is still being written
    return s if cut < 0 else s[:cut] + marker


class SentenceFeeder:
    """Speaks a reply sentence by sentence while the model is still writing it, so the voice starts in a couple of seconds."""

    def __init__(self, speaker):
        import re
        self.speaker, self.done, self.said = speaker, 0, ""
        self.end = re.compile(r'[.!?…]["”)]*\s')

    def feed(self, text):
        s = speakable(text)
        while True:
            m = self.end.search(s, self.done)
            if not m:
                return
            chunk = s[self.done:m.end()].strip()
            self.done = m.end()
            if chunk:
                self.said += chunk
                self.speaker.speak(chunk)

    def finish(self, text, done=None):
        """The reply is complete: speak what is left and call done() after the last word. If the final text is not what was streamed, start over."""
        s = speakable(text)
        if self.said and not s.replace(" ", "").startswith(self.said.replace(" ", "")):
            self.speaker.stop()
            self.done, self.said = 0, ""
        rest = s[self.done:].strip()
        self.done = len(s)
        if rest:
            self.speaker.speak(rest, done)
        elif done:
            self.speaker.after(done)


def ensure_vosk(progress=lambda p: None):
    """Downloads the small Portuguese recognizer (~31 MB) once. Returns its folder."""
    for cand in [VOSK_DIR, *VOSK_DIR.glob("*")]:
        if (cand / "am" / "final.mdl").exists() or (cand / "final.mdl").exists():
            return cand
    VOSK_DIR.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(VOSK_URL, timeout=60) as r:
        total = int(r.headers.get("Content-Length", 0))
        data = bytearray()
        while chunk := r.read(1 << 18):
            data += chunk
            if total:
                progress(int(len(data) * 100 / total))
    zipfile.ZipFile(io.BytesIO(bytes(data))).extractall(VOSK_DIR)
    return ensure_vosk()


def apply_gain(samples, target_peak=9000.0, max_gain=40.0):
    """Automatic volume for a quiet microphone: scales a block so its loudest part reaches target_peak. Returns (int16 array, gain)."""
    import numpy as np
    x = samples.astype(np.float32)
    peak = float(np.percentile(np.abs(x), 99.5)) if len(x) else 0.0
    gain = 1.0 if peak < 40 else min(max_gain, max(1.0, target_peak / peak))  # below 40 it is just hiss: don't boost it
    return np.clip(x * gain, -32768, 32767).astype(np.int16), gain


HEADSET_WORDS = ("headset", "fone", "headphone", "auricular", "hands-free", "handsfree", "bluetooth", "usb")


def input_devices():
    """[(index, name)] of the microphones Windows offers (MME list, the one Windows itself orders). Re-reads the device list every time."""
    import sounddevice as sd
    try:
        sd._terminate()
        sd._initialize()
    except Exception:
        pass
    out, seen = [], set()
    for i, d in enumerate(sd.query_devices()):
        if d.get("max_input_channels", 0) > 0 and d.get("hostapi") == 0:
            key = d["name"].strip().lower()
            if key not in seen and "mapper" not in key and "mapeador" not in key:
                seen.add(key)
                out.append((i, d["name"].strip()))
    return out


def devices_signature():
    """Changes when a headset is plugged in or removed (cheap: asks Windows' wave-in list, no audio library re-initialisation)."""
    try:
        return ctypes.windll.winmm.waveInGetNumDevs()
    except Exception:
        return 0


def default_microphone(preferred="", skip=()):
    """(index, name) of the microphone to use now. Order: the one he picked in the Microfone window, the one Windows has as default, then any other
    (headsets first), skipping the ones that were silent. The device list is re-read each time, so plugging a headset is followed."""
    import sounddevice as sd
    try:
        devices = input_devices()
        if not devices:
            return None, "microfone padrão"
        if preferred:
            for i, n in devices:
                if preferred.lower() in n.lower():
                    return i, n
        default = sd.default.device[0]
        if default is None or default < 0:
            default = sd.query_hostapis(0)["default_input_device"]
        if default not in skip and default >= 0:
            return default, sd.query_devices(default)["name"]
        rest = [(i, n) for i, n in devices if i not in skip]
        rest.sort(key=lambda d: not any(w in d[1].lower() for w in HEADSET_WORDS))
        if rest:
            return rest[0]
        skip.clear() if hasattr(skip, "clear") else None
        return default, sd.query_devices(default)["name"]
    except Exception:
        return None, "microfone padrão"


class Listener:
    """Microphone → text, offline. Always uses the microphone Windows has as default at that moment."""
    RATE = 16000

    def __init__(self):
        self.model = None
        self.cancel = threading.Event()
        self.device_name = ""
        self.device_index = None
        self.preferred = ""      # the microphone he chose in the Microfone window ("" = follow Windows)
        self.skip = set()        # microphones that were silent in this session: the next try uses another one
        self.peak = 0

    def _model(self, progress=lambda p: None):
        if self.model is None:
            from vosk import Model, SetLogLevel
            SetLogLevel(-1)
            self.model = Model(str(ensure_vosk(progress)))
        return self.model

    def preload(self, progress=lambda p: None):
        self._model(progress)

    def _stream(self, q):
        """An open microphone stream. Tries the chosen / default microphone; when a device cannot be opened (a headset that only offers its own
        sample rate or two channels, for instance) it adapts, and if it still fails it moves on to the next microphone."""
        import numpy as np, sounddevice as sd
        last = None
        for _ in range(6):
            idx, self.device_name = default_microphone(self.preferred, self.skip)
            self.device_index = idx
            try:
                info = sd.query_devices(idx) if idx is not None else sd.query_devices(kind="input")
            except Exception:
                info = {"default_samplerate": self.RATE, "max_input_channels": 1}
            native = int(info.get("default_samplerate") or self.RATE)
            for rate, channels in ((self.RATE, 1), (native, 1), (self.RATE, 2), (native, 2)):
                if channels > int(info.get("max_input_channels") or 1):
                    continue

                def cb(data, frames, t, status, rate=rate, channels=channels):
                    x = np.frombuffer(bytes(data), dtype=np.int16)
                    if channels > 1:
                        x = x[::channels]
                    if rate != self.RATE:   # a headset that only runs at its own rate: bring it to 16 kHz
                        n = int(len(x) * self.RATE / rate)
                        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x.astype(np.float32)).astype(np.int16)
                    q.put(x.tobytes())
                try:
                    stream = sd.RawInputStream(samplerate=rate, blocksize=int(rate * 0.2), dtype="int16", channels=channels, device=idx, callback=cb)
                    stream.start()
                    stream.stop()   # opened fine; the caller starts it through the context manager
                    return stream
                except Exception as e:
                    last = e
            if idx is None:
                break
            self.skip.add(idx)   # this one cannot be opened at all: try the next microphone
        raise RuntimeError(f"Não consegui abrir nenhum microfone ({last})")

    def _note_level(self):
        """A microphone that stayed silent is skipped next time (the headset may be the one that works); one that was heard stays."""
        if self.peak < 60 and self.device_index is not None and not self.preferred:
            self.skip.add(self.device_index)
        elif self.peak >= 200:
            self.skip.clear()

    def _block(self, data):
        """Amplifies a quiet block and remembers the loudest level heard (to explain a silent microphone)."""
        import numpy as np
        out, gain = apply_gain(np.frombuffer(data, dtype=np.int16))
        self.peak = max(self.peak, int(np.abs(np.frombuffer(data, dtype=np.int16)).max(initial=0)))
        return out.tobytes()

    def explain_silence(self):
        if self.peak < 60:
            return (f"O microfone \"{self.device_name}\" quase não capta som (nível {self.peak}). Na próxima vez tento outro microfone; "
                    "se preferir, escolha o certo em Microfone, no menu lateral, ou confira o volume em Configurações > Sistema > Som.")
        return f"Captei som em \"{self.device_name}\" mas não entendi nenhuma palavra. Fale um pouco mais perto e devagar."

    WHISPER_SIZE = "small"
    VOCAB = "Gota, Veeam, Windows, Linux, tela, cibersegurança, infraestrutura, backup, servidor, PowerShell, firewall, Active Directory."

    whisper_downloading = False

    def _whisper_dir(self):
        """Folder of the downloaded Whisper model, or None while it is not on this computer yet."""
        root = MODELS / "whisper"
        for d in root.glob(f"models--*whisper-{self.WHISPER_SIZE}*/snapshots/*"):
            if (d / "model.bin").exists():
                return d
        return None

    def whisper_ready(self):
        return self._whisper_dir() is not None

    def download_whisper(self):
        """Fetches the Whisper model in the background (about 480 MB, once). Until it is here, Vosk's text is used."""
        if self.whisper_downloading or self.whisper_ready():
            return
        self.whisper_downloading = True

        def work():
            try:
                from faster_whisper.utils import download_model
                root = MODELS / "whisper"
                root.mkdir(parents=True, exist_ok=True)
                download_model(self.WHISPER_SIZE, cache_dir=str(root))
            except Exception:
                pass
            finally:
                self.whisper_downloading = False
        threading.Thread(target=work, daemon=True).start()

    def whisper(self):
        if getattr(self, "_whisper", None) is None:
            from faster_whisper import WhisperModel
            folder = self._whisper_dir()
            if folder is None:
                raise RuntimeError("modelo Whisper ainda não baixado")
            self._whisper = WhisperModel(str(folder), device="cpu", compute_type="int8", cpu_threads=8)
        return self._whisper

    def refine(self, audio: bytes, fallback: str) -> str:
        """Re-transcribes the whole sentence with Whisper (far more accurate than Vosk); keeps Vosk's text if it fails."""
        import numpy as np
        if not fallback or len(audio) < self.RATE * 2 * 0.3 or not self.whisper_ready():  # never wait for a download in the middle of a sentence
            return fallback
        try:
            x = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
            segs, _ = self.whisper().transcribe(x, language="pt", beam_size=5, vad_filter=True, initial_prompt=self.VOCAB, condition_on_previous_text=False)
            text = " ".join(s.text.strip() for s in segs).strip()
            if text and not text.lower().startswith(self.VOCAB[:12].lower()):
                return text
        except Exception:
            pass
        return fallback

    def preload(self, progress=lambda p: None):
        self._model(progress)
        try:
            if self.whisper_ready():
                self.whisper()
        except Exception:
            pass

    def listen(self, on_partial=lambda t: None, silence=1.2, timeout=8.0, max_seconds=30.0, on_level=lambda p: None):
        """Waits for speech, returns the sentence once there is a pause (or "" if nobody spoke). Blocking."""
        from vosk import KaldiRecognizer
        rec = KaldiRecognizer(self._model(), self.RATE)
        self.cancel.clear()
        self.peak = 0
        q = queue.Queue()
        started, last_voice, heard = time.time(), None, ""
        buf = bytearray()
        with self._stream(q):
            while not self.cancel.is_set():
                try:
                    data = self._block(q.get(timeout=0.3))
                except queue.Empty:
                    data = b""
                now = time.time()
                if data:
                    on_level(self.peak)
                    buf += data
                if data and rec.AcceptWaveform(data):
                    text = json.loads(rec.Result()).get("text", "")
                    if text:
                        return self.refine(bytes(buf), text)
                elif data:
                    part = json.loads(rec.PartialResult()).get("partial", "")
                    if part:
                        heard, last_voice = part, now
                        on_partial(part)
                if last_voice is None and now - started > timeout:
                    self._note_level()
                    return ""
                if last_voice is not None and now - last_voice > silence or now - started > max_seconds:
                    return self.refine(bytes(buf), json.loads(rec.FinalResult()).get("text", "") or heard)
        return ""

    def wait_for_wake_word(self, stop: threading.Event):
        """Blocks until someone says 'Hey Gota' (or stop is set). Returns True when heard. When a headset is plugged in or removed the
        microphone is reopened on the right device."""
        from vosk import KaldiRecognizer
        while not stop.is_set():
            rec = KaldiRecognizer(self._model(), self.RATE, WAKE_GRAMMAR)
            q = queue.Queue()
            signature, checked = devices_signature(), time.time()
            with self._stream(q):
                while not stop.is_set():
                    if time.time() - checked > 2:
                        checked = time.time()
                        if devices_signature() != signature:
                            self.skip.clear()
                            break   # the set of microphones changed: reopen
                    try:
                        data = self._block(q.get(timeout=0.3))
                    except queue.Empty:
                        continue
                    if rec.AcceptWaveform(data):
                        if "gota" in json.loads(rec.Result()).get("text", ""):
                            return True
        return False


class Hotkey:
    """A global shortcut that works over any program (RegisterHotKey), e.g. 'ctrl+alt+g'."""
    MODS = {"alt": 1, "ctrl": 2, "shift": 4, "win": 8}

    def __init__(self, combo, callback):
        self.callback = callback
        parts = [p.strip().lower() for p in combo.split("+")]
        self.mods = sum(self.MODS[p] for p in parts[:-1]) | 0x4000  # no auto-repeat
        key = parts[-1]
        self.vk = ord(key.upper()) if len(key) == 1 else {"space": 0x20, "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f8": 0x77}[key]
        self.thread_id = None
        self.ok = threading.Event()
        self.registered = False
        threading.Thread(target=self._loop, daemon=True).start()
        self.ok.wait(2)

    def _loop(self):
        u = ctypes.windll.user32
        self.thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        self.registered = bool(u.RegisterHotKey(None, 1, self.mods, self.vk))
        self.ok.set()
        msg = wintypes.MSG()
        while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312:
                try:
                    self.callback()
                except Exception:
                    pass

    def stop(self):
        if self.thread_id:
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)
