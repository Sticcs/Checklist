import sys
from pathlib import Path

# Repo layout on disk (dev, tests, Docker/Render deploy): backend/app/paths.py
# -> parent.parent.parent is the repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# PyInstaller-frozen builds set both of these; nothing else does.
_FROZEN = getattr(sys, "frozen", False)
_BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", "")) if _FROZEN else None


def is_desktop_build() -> bool:
    """True only inside the actual packaged desktop app (a frozen PyInstaller
    build) - never in local dev, tests, or the real deployed server. This is
    exactly the boundary the login-time web-account bootstrap and the
    sidebar's "Sync now" button (app/routers/auth.py) need: syncing "from the
    website into the app" is meaningless anywhere except the app itself."""
    return _FROZEN


def resource_path(*parts: str) -> Path:
    """A read-only bundled resource (e.g. the built frontend) - inside the
    PyInstaller bundle when frozen (see checklist.spec's `datas`), otherwise
    the same path in the repo.

    Resolved (symlinks followed) before returning: a macOS onedir .app
    bundle lays out `Contents/Frameworks/<name>` as a symlink to the real
    `Contents/Resources/<name>`, and sys._MEIPASS points at the Frameworks
    side. main.py's static-file route resolves each *candidate* file path
    before checking it's still inside this directory (`is_relative_to`) -
    resolving there follows the symlink to the Resources-side real path,
    but comparing it against an unresolved Frameworks-side base never
    matches, since is_relative_to is a plain path-component comparison, not
    symlink-aware. Every asset request failed that check and silently fell
    through to the index.html fallback (right HTTP status, wrong body - a
    .js request got HTML back), which is what made the packaged macOS app
    render as a blank white window despite the server, navigation, and
    webview attachment all genuinely working. Resolving once here keeps
    every caller consistent instead of requiring each one to remember to."""
    base = _BUNDLE_DIR if _FROZEN else _REPO_ROOT
    return base.joinpath(*parts).resolve()


def user_data_dir() -> Path:
    """Where the desktop app's own SQLite database lives. Unset (dev, tests,
    server deploy) keeps using the plain repo-root checklist.db exactly as
    before - only a frozen desktop build gets redirected to a per-user,
    writable data folder (the platform's own convention - AppData on
    Windows, Application Support on macOS), since the PyInstaller bundle
    itself is read-only and shouldn't hold state anyway."""
    if not _FROZEN:
        return _REPO_ROOT
    import os

    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    data_dir = base / "Checklist"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir
