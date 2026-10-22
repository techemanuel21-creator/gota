"""Coding projects: the folders you work on with Gota (created here, or imported from any other tool or AI)."""
import re, shutil, subprocess, time
from pathlib import Path

NOFLASH = 0x08000000


def _key(path):
    return str(Path(path).resolve()).lower()


def all_projects(settings):
    return list(settings.get("projects") or [])


def recent(settings):
    return sorted((p for p in all_projects(settings) if Path(p["path"]).exists()), key=lambda p: -p.get("last", 0))


def register(settings, path, name=None):
    """Adds the folder to the list (or refreshes it). Returns the project record."""
    path = str(Path(path).resolve())
    projects = all_projects(settings)
    found = next((p for p in projects if _key(p["path"]) == _key(path)), None)
    if found is None:
        found = {"name": name or Path(path).name, "path": path, "created": time.time()}
        projects.append(found)
    found["last"] = time.time()
    settings.set("projects", projects)
    return found


def forget(settings, path):
    settings.set("projects", [p for p in all_projects(settings) if _key(p["path"]) != _key(path)])


def safe_name(name):
    """A folder name from what the user typed: letters, digits, dash, underscore."""
    n = re.sub(r"[^\w\- ]+", "", name, flags=re.U).strip().replace(" ", "-")
    return n[:60] or "novo-projeto"


def create(parent, name, description=""):
    """Creates parent/name with a README (and a git repository when git exists). Returns the new folder."""
    folder = Path(parent) / safe_name(name)
    if folder.exists() and any(folder.iterdir()):
        raise FileExistsError(f"A pasta {folder} já existe e não está vazia.")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "README.md").write_text(f"# {name.strip()}\n\n{description.strip()}\n", "utf-8")
    if shutil.which("git"):
        try:
            subprocess.run(["git", "init", "-q"], cwd=folder, capture_output=True, timeout=30, creationflags=NOFLASH)
        except Exception:
            pass
    return folder
