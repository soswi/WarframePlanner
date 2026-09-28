"""Export to and import from a portable JSON payload."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from ..models import PlannerError, Task
from ..storage import Repository
from .definitions import DefinitionService
from .settings import SettingsService
from .tasks import TaskService

EXPORT_SCHEMA_VERSION = 2

#: Settings that describe where a recurrence window last landed. They belong to
#: the machine that produced them, not to the data, so they are never imported.
TRANSIENT_SETTING_PREFIX = "reset_marker:"


class TransferService:
    """Whole-store export, and import in either replace or merge mode."""

    def __init__(
        self,
        repo: Repository,
        tasks: TaskService,
        definitions: DefinitionService,
        settings: SettingsService,
    ) -> None:
        self.repo = repo
        self.tasks = tasks
        self.definitions = definitions
        self.settings = settings

    def export(self) -> dict[str, Any]:
        """Return the full contents of the store as a JSON-ready mapping."""
        return {
            "schema_version": EXPORT_SCHEMA_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "tasks": [task.to_dict() for task in self.repo.list_tasks()],
            "definitions": self.definitions.grouped(),
            "settings": self.settings.all(),
        }

    def import_payload(self, payload: dict[str, Any], merge: bool = False) -> dict[str, int]:
        """Load a payload produced by `export`.

        Args:
            payload: Parsed file contents.
            merge: Fold into the existing store rather than replacing it.

        Returns:
            Mapping with the number of tasks read from the file.

        Raises:
            PlannerError: If the file comes from a newer schema.
        """
        version = int(payload.get("schema_version", 0))
        if version > EXPORT_SCHEMA_VERSION:
            raise PlannerError(
                f"This file comes from a newer version of the app (schema {version})."
            )

        incoming = [Task.from_dict(raw) for raw in payload.get("tasks", [])]

        if merge:
            self._merge_tasks(incoming)
        else:
            self.repo.replace_tasks(incoming)
            self.settings.save({
                key: value
                for key, value in (payload.get("settings") or {}).items()
                if not key.startswith(TRANSIENT_SETTING_PREFIX)
            })

        # Definitions are applied in both modes. A merge that dropped them left
        # no way to repair a damaged palette short of replacing every task too.
        self.definitions.save_many(payload.get("definitions") or {})

        self.tasks.normalise_positions()
        return {"tasks": len(incoming)}

    def _merge_tasks(self, incoming: list[Task]) -> None:
        """Fold imported tasks into the existing set, updating rather than copying.

        A task is treated as the same task when it carries the same id, or
        failing that the same activity name. Only genuinely new tasks are
        inserted, and only they can be renumbered. Each existing task absorbs at
        most one incoming task, so a file holding two rows with the same name
        adds the second instead of overwriting the first twice.
        """
        existing = self.repo.list_tasks()
        by_id = {task.id: task for task in existing}
        by_name: dict[str, Task] = {}
        for task in existing:
            key = task.activity.strip().lower()
            if key:
                by_name.setdefault(key, task)

        taken = set(by_id)
        next_free = max(taken | {self.settings.min_task_id() - 1}) + 1

        claimed: set[int] = set()
        remap: dict[int, int] = {}
        plan: list[tuple[Task, int, Optional[int]]] = []

        for task in incoming:
            target = by_id.get(task.id)
            if target is None:
                key = task.activity.strip().lower()
                target = by_name.get(key) if key else None
            if target is not None and target.id in claimed:
                target = None

            if target is not None:
                claimed.add(target.id)
                remap[task.id] = target.id
                # Keep the slot the task already occupies rather than reshuffling.
                plan.append((task, target.id, target.position))
            else:
                new_id = task.id
                if new_id in taken:
                    new_id = next_free
                    next_free += 1
                taken.add(new_id)
                remap[task.id] = new_id
                plan.append((task, new_id, None))

        for task, new_id, position in plan:
            task.id = new_id
            task.dependencies = [remap.get(dep, dep) for dep in task.dependencies]
            if position is not None:
                task.position = position
            self.repo.upsert_task(task)
