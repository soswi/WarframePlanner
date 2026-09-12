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
        ("Done", "#39fe74"),
        ("In Progress", "#4d91fe"),
        ("Stuck", "#ec4657"),
        ("Active", "#1ce9db"),
    ],
    "priority": [
        ("High", "#fda817"),
        ("Medium", "#ffc370"),
        ("Low", "#9ac4fe"),
        ("Very High", "#ec4657"),
    ],
    "category": [
        ("Void Fissure", "#fda817"),
        ("Credits", "#0f97ff"),
        ("Platinum", "#c7eeff"),
        ("Resources", "#9ea39e"),
        ("Build", "#39fe74"),
        ("Standing", "#552ef5"),
        ("Preparation", "#e64777"),
        ("Event", "#f472b6"),
        ("Clan", "#c084fc"),
        ("Alliance", "#fe4876"),
        ("Level Up", "#20ee9f"),
        ("Mastery Rank", "#e879f9"),
        ("Kuva", "#ff2e43"),
        ("Grind", "#8a14ff"),
    ],
}

DEFAULT_SETTINGS = {
    "done_status": "Done",
    "reset_status": "In Progress",
    "min_task_id": "1000",
    "theme": "zariman",
    "layout": "table",
    "enforce_dependency_gate": "true",
    # Status pinned to the front of every list and given a colour accent.
    # Empty disables the behaviour.
    "highlight_status": "Active",
    "board_group_by": "status",
    "board_card_size": "comfortable",
}
