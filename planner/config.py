"""Where the application runs: bundled resources and per-user data."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "WarframePlanner"
APP_TITLE = "Warframe Activity & Operations Planner"


def resource_dir() -> Path:
    """Root of packaged resources, or the source tree when running unfrozen."""
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled) / "planner"
    return Path(__file__).resolve().parent


def data_dir() -> Path:
    """Per-user writable directory. Survives replacing the executable."""
    override = os.environ.get("WARFRAME_PLANNER_DATA")
    if override:
        path = Path(override)
    elif sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home())
        path = Path(base) / APP_NAME
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    """Path to the SQLite file holding every task and setting."""
    return data_dir() / "planner.db"


def static_dir() -> Path:
    """Directory served at ``/static``."""
    return resource_dir() / "static"
