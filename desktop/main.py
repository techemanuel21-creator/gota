"""Gota Local Assistant for Windows."""
import ctypes, sys

try:   # sharp text on high-DPI screens, and every monitor reported and captured in its own real pixels (per-monitor v2)
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

try:   # own identity for the taskbar: shows the Gota icon (not Python's) when it runs from source through pythonw
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Gota.Desktop")
except Exception:
    pass


def selftest():
    """python main.py --selftest : checks the pieces that only break in the packaged program, writes selftest.txt."""
    import traceback
    lines = []
    def check(name, fn):
        try:
            lines.append(f"OK   {name}: {fn()}")
        except Exception:
            lines.append(f"FAIL {name}\n{traceback.format_exc()}")
    def image():
        from gota import imagegen
        g = imagegen.ImageGen()
        if not g.ready():
            return "modelo do pintor ainda não baixado (normal em instalação nova)"
        return str(g.generate("a red apple on a wooden table"))
    def vosk():
        from gota import voice
        return str(voice.ensure_vosk().name)
    def piper():
        from gota import voice
        return str(voice.ensure_piper_voice())
    def llm_import():
        import litert_lm
        return litert_lm.__name__
    def mic():
        from gota import voice
        return voice.default_microphone()[1]
    def skills_check():
        from gota import skills
        found = skills.load_all()
        assert found, "nenhuma habilidade encontrada"
        return f"{len(found)} habilidades"
    def kbase():
        from gota import kb
        kb.install_seed()
        return f"{len(kb.listing())} notas"
    def docs():
        import pypdf, openpyxl, docx, fpdf, psutil
        return "pypdf openpyxl docx fpdf psutil"
    def whisper():
        import faster_whisper, ctranslate2
        return f"faster-whisper {faster_whisper.__version__}, modelo {'baixado' if __import__('gota.voice', fromlist=['x']).Listener().whisper_ready() else 'ainda não baixado (baixa sozinho)'}"
    def outlook_check():
        import msal
        from gota import outlook
        raw = b"teste"
        assert outlook._crypt(outlook._crypt(raw, True), False) == raw
        return f"msal {msal.__version__}, criptografia do token ok"
    def vscode_check():
        from gota import vscode, server, projects
        assert (vscode.extension_source() / "package.json").exists(), "extensão do Gota ausente"
        return f"extensão empacotada; VS Code {'instalado' if vscode.find_code() else 'não instalado (o Gota oferece instalar)'}"
    def whatsapp_check():
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page()
            page.goto("about:blank")
            version = browser.version
            browser.close()
        return f"Playwright + Edge {version}"
    for name, fn in (("litert_lm", llm_import), ("microfone", mic), ("base de conhecimento", kbase), ("habilidades", skills_check), ("documentos", docs), ("voz Piper", piper), ("Vosk", vosk), ("Whisper", whisper),
                     ("Outlook", outlook_check), ("WhatsApp (navegador)", whatsapp_check), ("VS Code", vscode_check), ("imagem", image)):
        check(name, fn)
    from gota.store import ROOT
    (ROOT / "selftest.txt").write_text("\n".join(lines), "utf-8")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
        sys.exit(0)
    # one copy at a time: a second launch just brings the first one back is not possible without a server, so refuse politely
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "GotaLocalAssistantSingleton")
    if ctypes.windll.kernel32.GetLastError() == 183:
        ctypes.windll.user32.MessageBoxW(None, "O Gota já está aberto (veja o ícone perto do relógio).", "Gota", 0x40)
        sys.exit(0)
    from gota.app import App
    App().mainloop()
