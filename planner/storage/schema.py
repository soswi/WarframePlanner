"""Table definitions and the current schema version.

Bumping ``DB_SCHEMA_VERSION`` without adding a matching step in
`planner.storage.migrations` will leave existing databases untouched.
"""

from __future__ import annotations

DB_SCHEMA_VERSION = 8

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
