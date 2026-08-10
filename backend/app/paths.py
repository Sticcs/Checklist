import sys
from pathlib import Path

# Repo layout on disk (dev, tests, Docker/Render deploy): backend/app/paths.py
# -> parent.parent.parent is the repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# PyInstaller-frozen builds set both of these; nothing else does.
_FROZEN = getattr(sys, "frozen", False)
_BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", "")) if _FROZEN else None


def resource_path(*parts: str) -> Path:
    """A read-only bundled resource (e.g. the built frontend) - inside the
    PyInstaller bundle when frozen (see checklist.spec's `datas`), otherwise
    the same path in the repo."""
    base = _BUNDLE_DIR if _FROZEN else _REPO_ROOT
    return base.joinpath(*parts)


def user_data_dir() -> Path:
    """Where the desktop app's own SQLite database lives. Unset (dev, tests,
    server deploy) keeps using the plain repo-root checklist.db exactly as
    before - only a frozen desktop build gets redirected to a per-user,
    writable AppData folder, since the PyInstaller bundle itself is
    read-only and shouldn't hold state anyway."""
    if not _FROZEN:
        return _REPO_ROOT
    import os

    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    data_dir = Path(base) / "Checklist"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir
