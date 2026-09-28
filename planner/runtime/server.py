"""Process lifecycle: single-instance handover, ports, streams and shutdown."""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Optional

import uvicorn

from ..web import APP_SIGNATURE, create_app
from ..config import data_dir, database_path
from ..storage import SqliteRepository
from ..domain import PlannerService

PREFERRED_PORT = 8731
PROBE_TIMEOUT_S = 1.5


def session_file() -> Path:
    return data_dir() / "session.json"


def ensure_streams() -> Optional[str]:
    """Give the process real stdout/stderr, and say where they went.

    A windowed PyInstaller build on Windows starts with sys.stdout and
    sys.stderr set to None. Anything that inspects them then fails: uvicorn's
    colourised formatter calls sys.stdout.isatty() and brings down startup
    before the server exists. Point them at a log file instead, which also
    makes a windowed build diagnosable at all.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return None

    log_path: Optional[Path] = data_dir() / "planner.log"
    try:
        stream = open(log_path, "a", encoding="utf-8", buffering=1)
    except OSError:
        stream = open(os.devnull, "w", encoding="utf-8")
        log_path = None

    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream
    return str(log_path) if log_path else None


def probe_running_instance() -> Optional[str]:
    """Return the URL of an instance that is already up, or None.

    Launching the executable again should hand the user back to the window they
    already have rather than starting a second server against the same
    database. The recorded address is verified over HTTP and checked for our own
    signature, so a stale file or an unrelated service on the same port is
    ignored rather than trusted.
    """
    path = session_file()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        url = payload["url"]
    except (OSError, ValueError, KeyError):
        return None

    try:
        with urllib.request.urlopen(f"{url}api/ping", timeout=PROBE_TIMEOUT_S) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        body = None

    if not body or body.get("app") != APP_SIGNATURE:
        # Nothing there, or something else entirely. Clear the stale record.
        try:
            path.unlink()
        except OSError:
            pass
        return None
    return url


def write_session(url: str, port: int) -> Optional[Path]:
    path = session_file()
    try:
        path.write_text(
            json.dumps({"url": url, "port": port, "pid": os.getpid()}, indent=2),
            encoding="utf-8",
        )
        return path
    except OSError:
        return None


def clear_session() -> None:
    try:
        session_file().unlink()
    except OSError:
        pass


def find_free_port(preferred: int = PREFERRED_PORT) -> int:
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return sock.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("No free port available.")


def build_service() -> PlannerService:
    """Single wiring point. Swap the repository here to change the storage backend."""
    return PlannerService(SqliteRepository(database_path()))


def main(open_browser: bool = True) -> None:
    log_path = ensure_streams()

    existing = probe_running_instance()
    if existing:
        print(f"Warframe Planner is already running at {existing}; reusing it.")
        if open_browser:
            webbrowser.open(existing)
        return

    service = build_service()
    service.apply_recurrence_resets()

    server: dict[str, uvicorn.Server] = {}

    def request_shutdown() -> None:
        instance = server.get("instance")
        if instance is not None:
            instance.should_exit = True

    app = create_app(service, on_shutdown=request_shutdown)

    port = find_free_port()
    url = f"http://127.0.0.1:{port}/"
    recorded = write_session(url, port)

    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    print(f"Warframe Planner: {url}")
    print(f"Database: {database_path()}")
    if recorded:
        print(f"Session file: {recorded}")
    if log_path:
        print(f"Logging to: {log_path}")

    # log_config=None keeps uvicorn from rebuilding its colourised logging
    # handlers, which assume an interactive terminal that a windowed build
    # does not have. Our own handlers above already cover the output.
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning",
                            log_config=None, access_log=False)
    server["instance"] = uvicorn.Server(config)
    try:
        server["instance"].run()
    finally:
        clear_session()
        print("Warframe Planner stopped.")


if __name__ == "__main__":
    main()
