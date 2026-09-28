"""Where an instance keeps its data, its session record and its log.

Production and the test environment are fully separate: different database,
different session file, different preferred port. Starting one never looks at
the other's records, so a test run cannot capture, block or reroute a normal
launch.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import data_dir

PRODUCTION_PORT = 8731
TEST_PORT = 8732

DATABASE_FILENAME = "planner.db"
PRODUCTION_SESSION_FILENAME = "session.json"
LOG_FILENAME = "planner.log"

#: Every test environment directory starts with this, which is also what the
#: cleanup guard checks before deleting anything.
TEST_DIR_PREFIX = "warframe-planner-test-"

#: Written into a test directory at creation. A directory without it is never
#: deleted, whatever its name.
TEST_MARKER_FILE = ".warframe-planner-test-env"

#: Points at a running test instance. Kept in the temp root under a fixed name,
#: so a second `--run-test-env` can find it without touching the user's data
#: directory in any way.
TEST_SESSION_FILENAME = "warframe-planner-test-session.json"

TEST_LABEL = "TEST ENV"


class UnsafeCleanupError(RuntimeError):
    """Raised instead of deleting a directory that fails any safety check."""


def temp_root() -> Path:
    """The operating system's temp directory."""
    return Path(tempfile.gettempdir())


@dataclass(frozen=True)
class RuntimeEnvironment:
    """Everything that differs between a production run and a test run.

    Attributes:
        storage_dir: Directory holding the database.
        session_file: Record of the running instance, used for handover.
        log_dir: Where output goes when the process has no console.
        preferred_port: Tried first; any free port is used if it is taken.
        is_test: True for a disposable environment.
        label: Shown in the interface when set.
    """

    storage_dir: Path
    session_file: Path
    log_dir: Path
    preferred_port: int
    is_test: bool = False
    label: str = ""

    @classmethod
    def production(cls) -> "RuntimeEnvironment":
        """The user's own data directory."""
        root = data_dir()
        return cls(
            storage_dir=root,
            session_file=root / PRODUCTION_SESSION_FILENAME,
            log_dir=root,
            preferred_port=PRODUCTION_PORT,
        )

    @classmethod
    def create_test(cls) -> "RuntimeEnvironment":
        """A fresh, empty environment in the system temp directory.

        Placed under the temp root rather than beside the user's data, so no
        path arithmetic in the cleanup can ever land on the real store.
        Leftovers from test runs that were killed rather than quit are swept
        first.
        """
        sweep_stale_test_dirs()
        path = Path(tempfile.mkdtemp(prefix=TEST_DIR_PREFIX))
        (path / TEST_MARKER_FILE).write_text(
            "Disposable Warframe Planner test environment. Safe to delete.\n",
            encoding="utf-8",
        )
        return cls(
            storage_dir=path,
            session_file=test_session_file(),
            log_dir=path,
            preferred_port=TEST_PORT,
            is_test=True,
            label=TEST_LABEL,
        )

    def database_path(self) -> Path:
        """SQLite file for this environment."""
        return self.storage_dir / DATABASE_FILENAME

    def log_path(self) -> Path:
        """Log file for a process started without a console."""
        return self.log_dir / LOG_FILENAME

    def describe(self) -> dict[str, Any]:
        """What the interface needs to know about the environment."""
        return {"test": self.is_test, "label": self.label}

    def cleanup(self) -> bool:
        """Delete a test environment. A no-op for production.

        Returns:
            True if a directory was removed.
        """
        if not self.is_test:
            return False
        assert_safe_to_delete(self.storage_dir)
        shutil.rmtree(self.storage_dir, ignore_errors=True)
        return True


def test_session_file() -> Path:
    """Fixed location of the test instance's session record."""
    return temp_root() / TEST_SESSION_FILENAME


def assert_safe_to_delete(path: Path) -> None:
    """Refuse to delete anything that is not unmistakably a test environment.

    Every check must pass. Each one on its own already rules out the user's
    store; together, deleting it would take several independent mistakes.

    Raises:
        UnsafeCleanupError: Naming the check that failed.
    """
    resolved = path.resolve()
    root = temp_root().resolve()
    real_store = data_dir().resolve()

    if not resolved.name.startswith(TEST_DIR_PREFIX):
        raise UnsafeCleanupError(f"Not a test directory name: {resolved}")
    if resolved.parent != root:
        raise UnsafeCleanupError(f"Not directly inside the temp root: {resolved}")
    if not (resolved / TEST_MARKER_FILE).is_file():
        raise UnsafeCleanupError(f"Test marker missing: {resolved}")
    if (resolved == real_store
            or real_store.is_relative_to(resolved)
            or resolved.is_relative_to(real_store)):
        raise UnsafeCleanupError(f"Overlaps the user's data directory: {resolved}")


def sweep_stale_test_dirs() -> int:
    """Remove test environments left behind by killed processes.

    Only called when no test instance is running, so none of these can be live.

    Returns:
        How many were removed.
    """
    removed = 0
    for candidate in temp_root().glob(f"{TEST_DIR_PREFIX}*"):
        if not candidate.is_dir():
            continue
        try:
            assert_safe_to_delete(candidate)
        except UnsafeCleanupError:
            continue
        shutil.rmtree(candidate, ignore_errors=True)
        removed += 1
    return removed
