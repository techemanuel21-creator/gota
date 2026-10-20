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

    def _run(self):
        import numpy as np, sounddevice as sd
        piper = self._load_piper()
        sapi = None if piper else self._load_sapi()
        self.male = piper is not None
        self.ready.set()
        while True:
            text, done, gen = self.q.get()
            try:
                if gen != self.generation or not text:   # an empty line only marks 'everything before me has been played'
                    continue
                if piper:
                    audio = b"".join(c.audio_int16_bytes for c in piper.synthesize(text, syn_config=self.cfg))
                    if gen == self.generation:
                        sd.play(np.frombuffer(audio, dtype=np.int16), piper.config.sample_rate)
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


def default_microphone():
    """Name of the microphone Windows uses right now (re-read each time, so changing the default in Windows is followed)."""
    import sounddevice as sd
    try:
        sd._terminate()
        sd._initialize()
        idx = sd.default.device[0]
        if idx is None or idx < 0:
            idx = sd.query_hostapis(0)["default_input_device"]
        return idx, sd.query_devices(idx)["name"]
    except Exception:
        return None, "microfone padrão"


class Listener:
    """Microphone → text, offline. Always uses the microphone Windows has as default at that moment."""
    RATE = 16000

    def __init__(self):
        self.model = None
        self.cancel = threading.Event()
        self.device_name = ""
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
        import sounddevice as sd
        idx, self.device_name = default_microphone()

        def cb(data, frames, t, status):
            q.put(bytes(data))
        return sd.RawInputStream(samplerate=self.RATE, blocksize=3200, dtype="int16", channels=1, device=idx, callback=cb)

    def _block(self, data):
        """Amplifies a quiet block and remembers the loudest level heard (to explain a silent microphone)."""
        import numpy as np
        out, gain = apply_gain(np.frombuffer(data, dtype=np.int16))
        self.peak = max(self.peak, int(np.abs(np.frombuffer(data, dtype=np.int16)).max(initial=0)))
        return out.tobytes()

    def explain_silence(self):
        if self.peak < 60:
            return f"O microfone \"{self.device_name}\" quase não capta som (nível {self.peak}). Confira se ele não está mudo e o volume de entrada, em Configurações > Sistema > Som."
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
                    return ""
                if last_voice is not None and now - last_voice > silence or now - started > max_seconds:
                    return self.refine(bytes(buf), json.loads(rec.FinalResult()).get("text", "") or heard)
        return ""

    def wait_for_wake_word(self, stop: threading.Event):
        """Blocks until someone says 'Hey Gota' (or stop is set). Returns True when heard."""
        from vosk import KaldiRecognizer
        rec = KaldiRecognizer(self._model(), self.RATE, WAKE_GRAMMAR)
        q = queue.Queue()
        with self._stream(q):
            while not stop.is_set():
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
