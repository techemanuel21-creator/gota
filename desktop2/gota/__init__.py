"""Gota Local Assistant."""
import os, sys


def _ensure_console_streams():
    """The packaged program has no console, so sys.stdout / sys.stderr are None and libraries that write to them
    (the image engine, loggers, tracebacks) crash. Give them a log file instead; it also keeps the errors that used to vanish."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        base = os.environ.get("GOTA_HOME") or os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Gota")
        os.makedirs(base, exist_ok=True)
        path = os.path.join(base, "gota.log")
        if os.path.exists(path) and os.path.getsize(path) > 2_000_000:  # keep it small: start over
            os.remove(path)
        log = open(path, "a", encoding="utf-8", errors="replace", buffering=1)
    except Exception:
        log = open(os.devnull, "w")
    if sys.stdout is None:
        sys.stdout = log
    if sys.stderr is None:
        sys.stderr = log


_ensure_console_streams()
