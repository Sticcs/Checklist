"""Entry point for the packaged desktop build (see checklist.spec).

Runs the same FastAPI app as the web deployment, just bound to localhost only
and shown in a native window instead of a browser tab - everything else
(routes, auth, the SQLite database) is unchanged.
"""

import socket
import threading
import time
import urllib.request

import uvicorn
import webview
from webview import FileDialog

from app.main import app


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_up(url: str, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=0.5)
            return
        except Exception:
            time.sleep(0.1)


def main() -> None:
    port = _free_port()
    url = f"http://127.0.0.1:{port}"

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    # Daemon thread: the moment the webview window closes and main() returns,
    # the process should exit without waiting on the server to shut down.
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    _wait_until_up(url)

    window = webview.create_window("Checklist", url, width=1400, height=900, min_size=(900, 600))

    # Whether there's unsaved work linked to a website account right now -
    # kept in sync by the page itself calling set_dirty_state() (see
    # ExitSavePrompt.tsx) whenever it changes, rather than on_closing asking
    # the page for it on the way out. That "ask on the way out" version is
    # what this replaced: window.events.closing runs synchronously on the
    # UI thread (should_lock=True in webview/event.py), and WebView2's
    # evaluate_js blocks that same thread on a semaphore waiting for a
    # continuation that's scheduled to run back on... the UI thread - which
    # can't happen while it's the one blocked. That's a real, reproducible
    # deadlock (confirmed by hand: the window simply stopped responding to
    # its own close button), not a hypothetical one - a plain push from the
    # page avoids ever calling evaluate_js from inside this handler.
    _save_state = {"should_prompt": False}

    def set_dirty_state(dirty: bool, linked: bool) -> None:
        _save_state["should_prompt"] = bool(dirty and linked)

    def on_closing() -> bool:
        if not _save_state["should_prompt"]:
            return True
        # Still can't call evaluate_js synchronously here for the same
        # deadlock reason - but on_closing returning False right away frees
        # the UI thread to keep pumping messages, so doing it on a plain
        # background thread (which only needs to *start* the call, not wait
        # out the whole close) works fine.
        threading.Thread(
            target=lambda: window.evaluate_js(
                "window.__checklistShowExitPrompt && window.__checklistShowExitPrompt()"
            ),
            daemon=True,
        ).start()
        return False

    window.events.closing += on_closing

    def close_app() -> None:
        # Called from the exit-save prompt once it's actually safe to close
        # (the save succeeded, or the user chose to discard changes).
        # Unregisters on_closing first - window.destroy() re-fires the same
        # native close event on its way out, and without this it would just
        # cancel itself and re-show the prompt instead of ever closing.
        window.events.closing -= on_closing
        window.destroy()

    def toggle_fullscreen() -> None:
        window.toggle_fullscreen()

    def save_export(filename: str, content: str) -> bool:
        # A plain <a href download> (what the website uses) can't be relied
        # on inside an embedded webview: there's no browser download manager
        # behind it, so WebView2/WKWebView either silently no-ops the click
        # or just navigates to the JSON instead of saving it - which is
        # exactly the "Export doesn't work" bug on both Windows and macOS.
        # The frontend fetches /api/export itself and hands the JSON text to
        # this instead (see DataBackupButtons/useIsDesktopApp), so the
        # actual file write goes through pywebview's own native save dialog,
        # which works identically on both platforms (see
        # frontend/src/components/DataBackupButtons.tsx).
        paths = window.create_file_dialog(FileDialog.SAVE, save_filename=filename)
        if not paths:
            return False
        path = paths if isinstance(paths, str) else paths[0]
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return True

    def notify(title: str, body: str) -> None:
        # The Notification Web API (what the website uses) isn't reliably
        # available inside an embedded webview - WKWebView in particular has
        # no notification permission UI to grant it through. plyer's
        # cross-platform native notification (Windows toast / macOS Notification
        # Center) is what useDueDateNotifications calls instead when running
        # in the desktop app.
        from plyer import notification

        notification.notify(title=title, message=body, app_name="Checklist", timeout=10)

    def expose_api() -> None:
        # Exposed to the page as window.pywebview.api.<name>(...) - see each
        # function's own comment for why it exists. Deliberately done here,
        # via expose() inside webview.start()'s callback, rather than
        # create_window(js_api=...): passing js_api at creation time made
        # pywebview eagerly probe window.native's WebView2 COM properties
        # from a background thread before the GUI's own thread had it ready,
        # which reliably hung the whole process (a recursive
        # "AccessibilityObject.Bounds" error storm, then the HTTP server
        # itself stopped responding - almost certainly the recursion pinning
        # the GIL). expose() after the GUI loop is already running sidesteps
        # that race entirely.
        window.expose(toggle_fullscreen, save_export, notify, close_app, set_dirty_state)

    webview.start(expose_api)


if __name__ == "__main__":
    main()
