"""SQLite implementation of `Repository`."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable, Optional

from ..defaults import DEFAULT_DEFINITIONS, DEFAULT_SETTINGS
from ..models import Definition, Task
from .base import Repository
from .migrations import migrate
from .schema import SCHEMA


class SqliteRepository(Repository):
    """Single-file storage for one user.

    Every method takes a reentrant lock: the connection is shared across the
    server's worker threads, and SQLite objects are not safe to use concurrently
    even with ``check_same_thread`` disabled.
    """

    def __init__(self, path: Path) -> None:
        """Open or create the database at ``path`` and bring it up to date.

        Args:
            path: File to open. Parent directories must already exist.
        """
        self._path = path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()
            migrate(self._conn)
        self._seed()

    def _seed(self) -> None:
        """Fill a fresh database with the shipped definitions and settings.

        Definitions are only written when none exist at all, so an emptied
        palette is not silently refilled. Settings are filled key by key, which
        lets a new setting appear in an existing database.
        """
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM definitions").fetchone()
            if row["n"] == 0:
                for kind, values in DEFAULT_DEFINITIONS.items():
                    for position, (value, color) in enumerate(values):
                        self._conn.execute(
                            "INSERT INTO definitions (kind, value, color, position) "
                            "VALUES (?,?,?,?)",
                            (kind, value, color, position),
                        )
            for key, value in DEFAULT_SETTINGS.items():
                self._conn.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", (key, value)
                )
            self._conn.commit()

    # ------------------------------------------------------------------ tasks

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> Task:
        """Build a task from a row, ignoring columns the model no longer has."""
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
        return [self._row_to_task(row) for row in rows]

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

        # Dangling references would surface as "Invalid ID" on tasks the user
        # never touched, so they are cleared here rather than reported.
        removed = set(ids)
        for task in self.list_tasks():
            kept = [dep for dep in task.dependencies if dep not in removed]
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
        return [Definition(**dict(row)) for row in rows]

    def replace_definitions(self, kind: str, definitions: Iterable[Definition]) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM definitions WHERE kind = ?", (kind,))
            for position, definition in enumerate(definitions):
                self._conn.execute(
                    "INSERT INTO definitions (kind, value, color, position) VALUES (?,?,?,?)",
                    (kind, definition.value, definition.color, position),
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
        return {row["key"]: row["value"] for row in rows}

    def close(self) -> None:
        """Close the underlying connection."""
        with self._lock:
            self._conn.close()
