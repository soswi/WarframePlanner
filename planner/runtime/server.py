"""Process lifecycle: single-instance handover, ports, streams and shutdown."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Optional, Sequence

import uvicorn

from ..domain import PlannerService
from ..storage import SqliteRepository
from ..web import APP_SIGNATURE, create_app
from .environment import RuntimeEnvironment

PROBE_TIMEOUT_S = 1.5
BROWSER_OPEN_DELAY_S = 1.0
HOST = "127.0.0.1"


# ------------------------------------------------------------------- streams

def ensure_streams(log_path: Optional[Path] = None) -> Optional[str]:
    """Give the process real stdout/stderr, and say where they went.

    A windowed PyInstaller build on Windows starts with sys.stdout and
    sys.stderr set to None. Anything that inspects them then fails: uvicorn's
    colourised formatter calls sys.stdout.isatty() and brings down startup
    before the server exists. Point them at a log file instead, which also
    makes a windowed build diagnosable at all.

    Args:
        log_path: File to write to. Defaults to the production log.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return None

    target: Optional[Path] = log_path or RuntimeEnvironment.production().log_path()
    try:
        stream = open(target, "a", encoding="utf-8", buffering=1)
    except OSError:
        stream = open(os.devnull, "w", encoding="utf-8")
        target = None

    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream
    return str(target) if target else None


# ------------------------------------------------------------------ sessions

def session_file(environment: Optional[RuntimeEnvironment] = None) -> Path:
    """Session record for an environment; production when none is given."""
    return (environment or RuntimeEnvironment.production()).session_file


def probe_running_instance(path: Optional[Path] = None) -> Optional[str]:
    """Return the URL of an instance that is already up, or None.

    Launching again should hand the user back to the window they already have
    rather than starting a second server against the same database. The
    recorded address is verified over HTTP and checked for our own signature,
    so a stale file or an unrelated service on the same port is ignored rather
    than trusted.

    Args:
        path: Session record to read. Defaults to production's.
    """
    path = path or session_file()
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


def write_session(url: str, port: int, path: Optional[Path] = None) -> Optional[Path]:
    """Record the running instance so a later launch can find it."""
    path = path or session_file()
    try:
        path.write_text(
            json.dumps({"url": url, "port": port, "pid": os.getpid()}, indent=2),
            encoding="utf-8",
        )
        return path
    except OSError:
        return None


def clear_session(path: Optional[Path] = None) -> None:
    """Remove a session record, ignoring one that is already gone."""
    try:
        (path or session_file()).unlink()
    except OSError:
        pass


def find_free_port(preferred: int) -> int:
    """Return ``preferred`` if it is free, otherwise any free port."""
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((HOST, port))
                return sock.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("No free port available.")


# ------------------------------------------------------------------ serving

def build_service(environment: Optional[RuntimeEnvironment] = None) -> PlannerService:
    """Single wiring point. Swap the repository here to change the storage backend."""
    environment = environment or RuntimeEnvironment.production()
    return PlannerService(SqliteRepository(environment.database_path()))


def serve(environment: RuntimeEnvironment, open_browser: bool = True) -> None:
    """Run the server against ``environment`` until it is asked to stop.

    The session record is always cleared on exit. A test environment's data is
    removed as well; production's never is, because `cleanup` refuses to act on
    anything that is not a test environment.
    """
    service = build_service(environment)
    service.apply_recurrence_resets()

    server: dict[str, uvicorn.Server] = {}

    def request_shutdown() -> None:
        instance = server.get("instance")
        if instance is not None:
            instance.should_exit = True

    app = create_app(service, on_shutdown=request_shutdown,
                     environment=environment.describe())

    port = find_free_port(environment.preferred_port)
    url = f"http://{HOST}:{port}/"
    recorded = write_session(url, port, environment.session_file)

    if open_browser:
        threading.Timer(BROWSER_OPEN_DELAY_S, lambda: webbrowser.open(url)).start()

    label = f" [{environment.label}]" if environment.label else ""
    print(f"Warframe Planner{label}: {url}")
    print(f"Database: {environment.database_path()}")
    if recorded:
        print(f"Session file: {recorded}")

    # log_config=None keeps uvicorn from rebuilding its colourised logging
    # handlers, which assume an interactive terminal that a windowed build
    # does not have.
    config = uvicorn.Config(app, host=HOST, port=port, log_level="warning",
                            log_config=None, access_log=False)
    server["instance"] = uvicorn.Server(config)
    try:
        server["instance"].run()
    finally:
        clear_session(environment.session_file)
        if environment.cleanup():
            print(f"Test environment removed: {environment.storage_dir}")
        print("Warframe Planner stopped.")


def hand_over(session: Path, open_browser: bool) -> bool:
    """Reuse an instance already running for this session, if there is one.

    Returns:
        True if an instance was found and the caller should exit.
    """
    existing = probe_running_instance(session)
    if not existing:
        return False
    print(f"Warframe Planner is already running at {existing}; reusing it.")
    if open_browser:
        webbrowser.open(existing)
    return True


def run_production(open_browser: bool = True) -> None:
    """The normal launch: the user's own data."""
    environment = RuntimeEnvironment.production()
    log_path = ensure_streams(environment.log_path())
    if log_path:
        print(f"Logging to: {log_path}")
    if hand_over(environment.session_file, open_browser):
        return
    serve(environment, open_browser)


def run_test_environment(open_browser: bool = True) -> None:
    """A disposable run on an empty database, removed again on quit.

    Looks only at the test session record, so it neither finds nor disturbs a
    production instance. The environment is created only after that check, so
    reusing a running test instance never builds a second, orphaned one.
    """
    from .environment import test_session_file

    if hand_over(test_session_file(), open_browser):
        return
    environment = RuntimeEnvironment.create_test()
    log_path = ensure_streams(environment.log_path())
    if log_path:
        print(f"Logging to: {log_path}")
    serve(environment, open_browser)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="WarframePlanner",
        description="Local task planner for Warframe activities.",
    )
    parser.add_argument(
        "--run-test-env",
        action="store_true",
        help="Run against a fresh, empty database that is deleted on quit. "
             "Your own data is never opened.",
    )
    # parse_known_args: PyInstaller and some launchers pass extra arguments of
    # their own, which must not stop the app from starting.
    args, _ = parser.parse_known_args(argv)
    return args


def main(argv: Optional[Sequence[str]] = None, open_browser: bool = True) -> None:
    """Entry point for `python main.py` and the packaged executable."""
    args = parse_args(argv)
    if args.run_test_env:
        run_test_environment(open_browser)
    else:
        run_production(open_browser)


if __name__ == "__main__":
    main()
