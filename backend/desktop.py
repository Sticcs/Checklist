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

    webview.create_window("Checklist", url, width=1400, height=900, min_size=(900, 600))
    webview.start()


if __name__ == "__main__":
    main()
