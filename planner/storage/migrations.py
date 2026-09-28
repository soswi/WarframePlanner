"""Forward-only schema and data migrations.

Every step is idempotent, so a run interrupted part-way is safe to repeat. The
version is tracked in SQLite's own ``user_version`` pragma rather than a table
of our own.
"""

from __future__ import annotations

import sqlite3

from ..defaults import DEFAULT_DEFINITIONS
from .schema import DB_SCHEMA_VERSION

# Every definition palette this application has ever shipped, keyed by kind.
# Each is written in its shipped display order; dicts keep insertion order.
#
# A migration replaces a palette only when it matches one of these exactly:
# value, colour AND order. Several releases kept the same names and changed only
# the colours, and one changed only the order, so a looser comparison would
# quietly discard a palette the user had recoloured or rearranged.
LEGACY_CATEGORIES = {
    "Void / Relics": "#a78bfa", "Void Fissure": "#a78bfa",
    "Void Resources": "#a78bfa", "Foundry": "#f472b6",
    "Duviri / Incarnon": "#fb923c", "Sanctum Anatomica": "#22d3ee",
    "Weekly Archon": "#facc15", "Sanctuary / Leveling": "#4ade80",
}

V3_CATEGORIES = {
    "Void Fissure": "#a78bfa", "Credits": "#facc15", "Platinum": "#38bdf8",
    "Resources": "#4ade80", "Build": "#fb923c", "Standing": "#22d3ee",
    "Preparation": "#94a3b8", "Event": "#f472b6", "Clan": "#c084fc",
    "Alliance": "#f87171",
}

V4_CATEGORIES = dict(V3_CATEGORIES, **{"Level Up": "#84cc16", "Mastery Rank": "#e879f9"})

V5_CATEGORIES = dict(V4_CATEGORIES, **{"Credits": "#38bdf8", "Platinum": "#7dd3fc"})

V6_CATEGORIES = dict(V5_CATEGORIES, **{
    "Void Fissure": "#fda817", "Credits": "#0f97ff", "Platinum": "#c7eeff",
    "Resources": "#9ea39e", "Build": "#39fe74", "Standing": "#552ef5",
    "Preparation": "#e64777", "Alliance": "#fe4876", "Level Up": "#20ee9f",
    "Kuva": "#ff2e43", "Grind": "#3300ff",
})

STOCK_PALETTES: dict[str, tuple[dict[str, str], ...]] = {
    "category": (
        LEGACY_CATEGORIES, V3_CATEGORIES, V4_CATEGORIES, V5_CATEGORIES, V6_CATEGORIES,
    ),
    "priority": (
        {"High": "#f59e0b", "Medium": "#0ea5e9", "Low": "#94a3b8"},
        # Shipped with Very High last; v8 moves it to the top.
        {"High": "#fda817", "Medium": "#ffc370", "Low": "#9ac4fe", "Very High": "#ec4657"},
    ),
    "status": (
        {"Done": "#10b981", "In Progress": "#3b82f6", "Stuck": "#ef4444"},
        {"Done": "#39fe74", "In Progress": "#4d91fe", "Stuck": "#ec4657"},
    ),
}


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Return the column names of ``table``."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def current_version(conn: sqlite3.Connection) -> int:
    """Return the schema version recorded in the database."""
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def migrate(conn: sqlite3.Connection) -> None:
    """Bring a database up to `DB_SCHEMA_VERSION`.

    Args:
        conn: Open connection with ``row_factory`` set to ``sqlite3.Row``.
    """
    version = current_version(conn)
    _split_dependency_column(conn)
    if version:
        _refresh_stock_palettes(conn, version)
    if version != DB_SCHEMA_VERSION:
        conn.execute(f"PRAGMA user_version = {DB_SCHEMA_VERSION}")
    conn.commit()


def _split_dependency_column(conn: sqlite3.Connection) -> None:
    """v1 to v2: a single ``dependency`` column becomes a JSON array."""
    columns = table_columns(conn, "tasks")
    if "dependency" not in columns:
        return

    if "dependencies" not in columns:
        conn.execute(
            "ALTER TABLE tasks ADD COLUMN dependencies TEXT NOT NULL DEFAULT '[]'"
        )
    conn.execute(
        "UPDATE tasks SET dependencies = '[' || dependency || ']' "
        "WHERE dependency IS NOT NULL AND dependencies = '[]'"
    )
    try:
        conn.execute("ALTER TABLE tasks DROP COLUMN dependency")
    except sqlite3.OperationalError:
        # SQLite before 3.35 cannot drop a column. The stale one is ignored when
        # rows are read, so leaving it in place is harmless.
        pass


def _refresh_stock_palettes(conn: sqlite3.Connection, version: int) -> None:
    """Replace any definition palette the user has left untouched.

    Each kind is judged on its own, so customising one does not freeze the
    others at an old palette.
    """
    if version >= DB_SCHEMA_VERSION:
        return

    for kind, shipped in STOCK_PALETTES.items():
        rows = conn.execute(
            "SELECT value, color FROM definitions WHERE kind = ? ORDER BY position",
            (kind,),
        ).fetchall()
        present = [(row["value"], row["color"]) for row in rows]
        if not any(present == list(palette.items()) for palette in shipped):
            continue

        conn.execute("DELETE FROM definitions WHERE kind = ?", (kind,))
        for position, (value, color) in enumerate(DEFAULT_DEFINITIONS[kind]):
            conn.execute(
                "INSERT INTO definitions (kind, value, color, position) VALUES (?,?,?,?)",
                (kind, value, color, position),
            )
