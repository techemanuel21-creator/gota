"""VS Code side of Gota: finds the editor, installs Gota's own extension, opens files and shows a proposed change as a side-by-side diff."""
import os, shutil, subprocess, sys, tempfile
from pathlib import Path

NOFLASH = 0x08000000
EXT_ID, EXT_VERSION = "gota.gota-vscode", "0.1.0"


def extension_source():
    base = getattr(sys, "_MEIPASS", None)
    root = Path(base) if base else Path(__file__).resolve().parent.parent
    return root / "vscode-extension" / "gota-vscode"


def extensions_dir():
    return Path.home() / ".vscode" / "extensions"


def find_code():
    """The `code` launcher, or None when VS Code is not installed."""
    found = shutil.which("code") or shutil.which("code.cmd")
    if found:
        return found
    for base in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")):
        for rel in ("Programs/Microsoft VS Code/bin/code.cmd", "Microsoft VS Code/bin/code.cmd"):
            p = Path(base) / rel if base else None
            if p and p.exists():
                return str(p)
    return None


def available():
    return find_code() is not None or extensions_dir().parent.exists()


def installed():
    return any(extensions_dir().glob(f"{EXT_ID}-*")) if extensions_dir().exists() else False


def install():
    """Copies Gota's extension into the user's VS Code extensions folder (it loads the next time VS Code starts). Returns the folder."""
    src = extension_source()
    if not (src / "package.json").exists():
        raise FileNotFoundError("a extensão do Gota não está junto do programa")
    dest_root = extensions_dir()
    dest_root.mkdir(parents=True, exist_ok=True)
    for old in dest_root.glob(f"{EXT_ID}-*"):
        shutil.rmtree(old, ignore_errors=True)
    dest = dest_root / f"{EXT_ID}-{EXT_VERSION}"
    shutil.copytree(src, dest)
    return dest


def uninstall():
    for old in extensions_dir().glob(f"{EXT_ID}-*") if extensions_dir().exists() else []:
        shutil.rmtree(old, ignore_errors=True)


def _run(args):
    code = find_code()
    if not code:
        raise FileNotFoundError("não achei o VS Code neste computador")
    subprocess.Popen([code, *args], creationflags=NOFLASH, shell=code.lower().endswith(".cmd"))


def open_path(path, line=None):
    """Opens a file (at a line) or a folder in VS Code."""
    p = Path(os.path.expandvars(os.path.expanduser(str(path))))
    if line and p.is_file():
        _run(["-g", f"{p}:{int(line)}"])
    else:
        _run([str(p)])
    return p


def diff_with_proposal(path, proposed_text):
    """Shows `path` next to a proposed new version in VS Code. The real file is NOT changed. Returns the temp file with the proposal."""
    p = Path(os.path.expandvars(os.path.expanduser(str(path))))
    tmp = Path(tempfile.mkdtemp(prefix="gota_proposta_")) / ("proposta_" + p.name)
    tmp.write_text(proposed_text, "utf-8")
    _run(["--diff", str(p), str(tmp)])
    return tmp


# ---------------------------------------------------------------- installing VS Code when it is missing
INSTALLER_URL = "https://update.code.visualstudio.com/latest/win32-x64-user/stable"   # Microsoft's official "user" installer: no administrator rights needed


def installer_info():
    """(final download URL, size in bytes) asked of Microsoft with a HEAD request; nothing is downloaded."""
    import urllib.request
    req = urllib.request.Request(INSTALLER_URL, method="HEAD", headers={"User-Agent": "GotaDesktop/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.geturl(), int(r.headers.get("Content-Length") or 0)


def install_vscode(progress=lambda pct: None):
    """Downloads Microsoft's installer and runs it silently (per user). Returns the path of `code` or None. Blocking: call from a thread."""
    import urllib.request
    folder = Path(tempfile.mkdtemp(prefix="gota_vscode_setup_"))
    try:
        exe = folder / "VSCodeUserSetup-x64.exe"
        with urllib.request.urlopen(urllib.request.Request(INSTALLER_URL, headers={"User-Agent": "GotaDesktop/1.0"}), timeout=60) as r, open(exe, "wb") as f:
            total, done = int(r.headers.get("Content-Length") or 0), 0
            while chunk := r.read(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total:
                    progress(int(done * 90 / total))
        progress(92)
        subprocess.run([str(exe), "/VERYSILENT", "/NORESTART", "/SUPPRESSMSGBOXES", "/MERGETASKS=!runcode,addtopath"], creationflags=NOFLASH, timeout=900)
        progress(100)
        return find_code()
    finally:
        shutil.rmtree(folder, ignore_errors=True)
