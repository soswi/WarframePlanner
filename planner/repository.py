from __future__ import annotations

import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterable, Optional

from .config import DEFAULT_DEFINITIONS, DEFAULT_SETTINGS
from .models import Definition, Task

DB_SCHEMA_VERSION = 4

# The category set shipped before v3. Used to tell an untouched default list
# apart from one the user has customised.
LEGACY_CATEGORIES = {
    "Void / Relics", "Void Fissure", "Void Resources", "Foundry",
    "Duviri / Incarnon", "Sanctum Anatomica", "Weekly Archon", "Sanctuary / Leveling",
}

# The category set shipped by v3, before Level Up and Mastery Rank were added.
V3_CATEGORIES = {
    "Void Fissure", "Credits", "Platinum", "Resources", "Build",
    "Standing", "Preparation", "Event", "Clan", "Alliance",
}

# Any stock list a migration is allowed to replace wholesale.
REPLACEABLE_CATEGORY_SETS = (LEGACY_CATEGORIES, V3_CATEGORIES)


class Repository(ABC):
    """Storage contract. A new backend (Postgres, flat file, remote API)
    only has to implement this interface; nothing above it changes."""

    @abstractmethod
    def list_tasks(self) -> list[Task]: ...

    @abstractmethod
    def upsert_task(self, task: Task) -> None: ...

    @abstractmethod
    def delete_tasks(self, ids: Iterable[int]) -> None: ...

    @abstractmethod
    def replace_tasks(self, tasks: Iterable[Task]) -> None: ...

    @abstractmethod
    def list_definitions(self) -> list[Definition]: ...

    @abstractmethod
    def replace_definitions(self, kind: str, definitions: Iterable[Definition]) -> None: ...

    @abstractmethod
    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]: ...

    @abstractmethod
    def set_setting(self, key: str, value: str) -> None: ...

    @abstractmethod
    def all_settings(self) -> dict[str, str]: ...


SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id            INTEGER PRIMARY KEY,
    activity      TEXT    NOT NULL DEFAULT '',
    category      TEXT    NOT NULL DEFAULT '',
    description   TEXT    NOT NULL DEFAULT '',
    priority      TEXT    NOT NULL DEFAULT '',
    status        TEXT    NOT NULL DEFAULT '',
    dependencies  TEXT    NOT NULL DEFAULT '[]',
    recurrence    TEXT    NOT NULL DEFAULT 'One-off',
    last_updated  TEXT,
    position      INTEGER NOT NULL DEFAULT 0,
    extra         TEXT    NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS definitions (
    kind     TEXT    NOT NULL,
    value    TEXT    NOT NULL,
    color    TEXT    NOT NULL DEFAULT '#94a3b8',
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (kind, value)
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class SqliteRepository(Repository):
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()
        self._migrate()
        self._seed()

    # ------------------------------------------------------------- migrations

    def _columns(self, table: str) -> set[str]:
        rows = self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {r["name"] for r in rows}

    def _migrate(self) -> None:
        """Bring an older database up to DB_SCHEMA_VERSION.

        Each step is idempotent, so a partially applied migration is safe to rerun.
        """
        with self._lock:
            current = self._conn.execute("PRAGMA user_version").fetchone()[0]
            columns = self._columns("tasks")

            # v1 -> v2: single `dependency` column becomes a `dependencies` JSON array.
            if "dependency" in columns:
                if "dependencies" not in columns:
                    self._conn.execute(
                        "ALTER TABLE tasks ADD COLUMN dependencies TEXT NOT NULL DEFAULT '[]'"
                    )
                self._conn.execute(
                    "UPDATE tasks SET dependencies = '[' || dependency || ']' "
                    "WHERE dependency IS NOT NULL AND dependencies = '[]'"
                )
                try:
                    self._conn.execute("ALTER TABLE tasks DROP COLUMN dependency")
                except sqlite3.OperationalError:
                    # SQLite older than 3.35 cannot drop columns; the stale column is
                    # ignored by _row_to_task, so leaving it in place is harmless.
                    pass

            # v2 -> v3 -> v4: the shipped category list changed twice. Replace it
            # only when it still matches a stock list exactly, so a customised
            # set is never overwritten.
            if current and current < DB_SCHEMA_VERSION:
                rows = self._conn.execute(
                    "SELECT value FROM definitions WHERE kind = 'category'"
                ).fetchall()
                present = {r["value"] for r in rows}
                if any(present == stock for stock in REPLACEABLE_CATEGORY_SETS):
                    self._conn.execute("DELETE FROM definitions WHERE kind = 'category'")
                    for pos, (value, color) in enumerate(DEFAULT_DEFINITIONS["category"]):
                        self._conn.execute(
                            "INSERT INTO definitions (kind, value, color, position) "
                            "VALUES (?,?,?,?)",
                            ("category", value, color, pos),
                        )

            if current != DB_SCHEMA_VERSION:
                self._conn.execute(f"PRAGMA user_version = {DB_SCHEMA_VERSION}")
            self._conn.commit()

    def _seed(self) -> None:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM definitions").fetchone()
            if row["n"] == 0:
                for kind, values in DEFAULT_DEFINITIONS.items():
                    for pos, (value, color) in enumerate(values):
                        self._conn.execute(
                            "INSERT INTO definitions (kind, value, color, position) "
                            "VALUES (?,?,?,?)",
                            (kind, value, color, pos),
                        )
            for key, value in DEFAULT_SETTINGS.items():
                self._conn.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", (key, value)
                )
            self._conn.commit()

    # ------------------------------------------------------------------ tasks

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> Task:
        known = set(Task.__dataclass_fields__)
        data: dict[str, Any] = {k: v for k, v in dict(row).items() if k in known}
        data["extra"] = json.loads(data.get("extra") or "{}")
        data["dependencies"] = json.loads(data.get("dependencies") or "[]")
        return Task(**data)

    def list_tasks(self) -> list[Task]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM tasks ORDER BY position ASC, id ASC"
            ).fetchall()
        return [self._row_to_task(r) for r in rows]

    def upsert_task(self, task: Task) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO tasks
                   (id, activity, category, description, priority, status,
                    dependencies, recurrence, last_updated, position, extra)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     activity=excluded.activity, category=excluded.category,
                     description=excluded.description, priority=excluded.priority,
                     status=excluded.status, dependencies=excluded.dependencies,
                     recurrence=excluded.recurrence, last_updated=excluded.last_updated,
                     position=excluded.position, extra=excluded.extra""",
                (
                    task.id, task.activity, task.category, task.description,
                    task.priority, task.status, json.dumps(task.dependencies),
                    task.recurrence, task.last_updated, task.position,
                    json.dumps(task.extra),
                ),
            )
            self._conn.commit()

    def delete_tasks(self, ids: Iterable[int]) -> None:
        ids = [int(i) for i in ids]
        if not ids:
            return
        placeholders = ",".join("?" * len(ids))
        with self._lock:
            self._conn.execute(f"DELETE FROM tasks WHERE id IN ({placeholders})", ids)
            self._conn.commit()
        # Strip the removed ids from every remaining dependency list.
        removed = set(ids)
        for task in self.list_tasks():
            kept = [d for d in task.dependencies if d not in removed]
            if kept != task.dependencies:
                task.dependencies = kept
                self.upsert_task(task)

    def replace_tasks(self, tasks: Iterable[Task]) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM tasks")
            self._conn.commit()
        for task in tasks:
            self.upsert_task(task)

    # ------------------------------------------------------------ definitions

    def list_definitions(self) -> list[Definition]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM definitions ORDER BY kind ASC, position ASC"
            ).fetchall()
        return [Definition(**dict(r)) for r in rows]

    def replace_definitions(self, kind: str, definitions: Iterable[Definition]) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM definitions WHERE kind = ?", (kind,))
            for pos, definition in enumerate(definitions):
                self._conn.execute(
                    "INSERT INTO definitions (kind, value, color, position) VALUES (?,?,?,?)",
                    (kind, definition.value, definition.color, pos),
                )
            self._conn.commit()

    # --------------------------------------------------------------- settings

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO settings (key, value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            self._conn.commit()

    def all_settings(self) -> dict[str, str]:
        with self._lock:
            rows = self._conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}

    def close(self) -> None:
        with self._lock:
            self._conn.close()
