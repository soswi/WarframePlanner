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
    return data_dir() / "planner.db"


def static_dir() -> Path:
    return resource_dir() / "static"


DEFAULT_DEFINITIONS = {
    "status": [
        ("Done", "#10b981"),
        ("In Progress", "#3b82f6"),
        ("Stuck", "#ef4444"),
    ],
    "priority": [
        ("High", "#f59e0b"),
        ("Medium", "#0ea5e9"),
        ("Low", "#94a3b8"),
    ],
    "category": [
        ("Void Fissure", "#a78bfa"),
        ("Credits", "#facc15"),
        ("Platinum", "#38bdf8"),
        ("Resources", "#4ade80"),
        ("Build", "#fb923c"),
        ("Standing", "#22d3ee"),
        ("Preparation", "#94a3b8"),
        ("Event", "#f472b6"),
        ("Clan", "#c084fc"),
        ("Alliance", "#f87171"),
        ("Level Up", "#84cc16"),
        ("Mastery Rank", "#e879f9"),
    ],
}

DEFAULT_SETTINGS = {
    "done_status": "Done",
    "reset_status": "In Progress",
    "min_task_id": "1000",
    "theme": "zariman",
    "layout": "table",
    "enforce_dependency_gate": "true",
    "board_group_by": "status",
    "board_card_size": "comfortable",
}
