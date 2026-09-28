"""Task lifecycle: creation, edits, ordering, duplication and recurrence resets."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional

from ..models import PlannerError, Task
from ..storage import Repository
from .dependencies import DependencyResolver
from .recurrence import RecurrenceRegistry
from .settings import SettingsService


def today_iso() -> str:
    """Today's date as ``YYYY-MM-DD`` in the machine's local timezone."""
    return date.today().isoformat()


class TaskService:
    """Everything that changes a task, and the ordering rules around it."""

    def __init__(
        self,
        repo: Repository,
        settings: SettingsService,
        dependencies: DependencyResolver,
        recurrence: RecurrenceRegistry,
    ) -> None:
        self.repo = repo
        self.settings = settings
        self.dependencies = dependencies
        self.recurrence = recurrence

    # ------------------------------------------------------------------ reads

    def list(self) -> list[dict[str, Any]]:
        """Return every task as a dict, enriched and ordered for display.

        Each entry gains ``prereq_status``, ``blocked_by``,
        ``missing_dependencies`` and ``highlighted``. Pinned tasks lead; the
        sort is stable, so everything else keeps its stored order.
        """
        tasks = self.repo.list_tasks()
        index = {task.id: task for task in tasks}
        highlight = self.settings.highlight_status()

        out = []
        for task in tasks:
            payload = task.to_dict()
            resolved = self.dependencies.resolve(task, index)
            payload["prereq_status"] = resolved["state"]
            payload["blocked_by"] = resolved["blocked_by"]
            payload["missing_dependencies"] = resolved["missing"]
            payload["highlighted"] = bool(highlight) and task.status == highlight
            out.append(payload)

        out.sort(key=lambda payload: not payload["highlighted"])
        return out

    def stats(self) -> dict[str, Any]:
        """Counts per status plus the completion ratio.

        The ratio is taken over tasks that carry a status. A task with none has
        not been triaged yet, and counting it would drag the rate down for
        reasons that say nothing about progress. ``total`` still counts every
        task.
        """
        tasks = self.repo.list_tasks()
        done_status = self.settings.done_status()

        counts: dict[str, int] = {}
        for task in tasks:
            if task.status:
                counts[task.status] = counts.get(task.status, 0) + 1

        rated = sum(counts.values())
        done = counts.get(done_status, 0)
        return {
            "total": len(tasks),
            "rated": rated,
            "counts": counts,
            "done": done,
            "completion_rate": (done / rated) if rated else 0.0,
        }

    def next_id(self) -> int:
        """Lowest unused id at or above the configured floor."""
        floor = self.settings.min_task_id()
        existing = [task.id for task in self.repo.list_tasks()]
        return max(existing + [floor - 1]) + 1

    # ----------------------------------------------------------------- writes

    def create(self, at_top: bool = True) -> dict[str, Any]:
        """Create an empty task.

        Args:
            at_top: Place it before every existing task rather than after.
        """
        tasks = self.repo.list_tasks()
        task = Task(id=self.next_id(), recurrence="One-off")
        if at_top:
            task.position = (min(t.position for t in tasks) - 1) if tasks else 0
        else:
            task.position = (max(t.position for t in tasks) + 1) if tasks else 0

        self.repo.upsert_task(task)
        self.normalise_positions()
        return task.to_dict()

    def update(self, task_id: int, changes: dict[str, Any]) -> dict[str, Any]:
        """Apply a partial update.

        Keys outside `Task.EDITABLE_FIELDS` are ignored rather than rejected, so
        a newer client cannot corrupt an older server.

        Raises:
            PlannerError: If the task is unknown, a dependency edit is invalid,
                or the completion gate refuses the new status.
        """
        index = {task.id: task for task in self.repo.list_tasks()}
        task = index.get(task_id)
        if task is None:
            raise PlannerError(f"Task {task_id} does not exist.")

        for key, value in changes.items():
            if key not in Task.EDITABLE_FIELDS:
                continue

            if key == "dependencies":
                task.dependencies = self.dependencies.validate(task, value, index)
            elif key == "status":
                if value != task.status:
                    self.dependencies.assert_status_allowed(task, value, index)
                    task.status = value
                    task.last_updated = today_iso()
            elif key == "recurrence":
                if value not in self.recurrence.keys():
                    raise PlannerError(f"Unknown recurrence: {value}")
                task.recurrence = value
            else:
                setattr(task, key, value)

        self.repo.upsert_task(task)
        return task.to_dict()

    def duplicate(self, ids: Iterable[int]) -> list[int]:
        """Copy tasks, each landing directly below its source.

        Dependencies are kept rather than remapped: a copy of "farm relics"
        still waits on the same prerequisite. Status and last-updated are
        cleared, because a copy has not been worked on yet.

        Returns:
            Ids of the newly created tasks.
        """
        index = {task.id: task for task in self.repo.list_tasks()}
        wanted = [int(i) for i in ids if int(i) in index]
        if not wanted:
            return []

        next_id = self.next_id()
        created: list[int] = []
        for source_id in wanted:
            source = index[source_id]
            copy = Task(
                id=next_id,
                activity=f"{source.activity} (copy)" if source.activity else "",
                category=source.category,
                description=source.description,
                priority=source.priority,
                status="",
                dependencies=list(source.dependencies),
                recurrence=source.recurrence,
                last_updated=None,
                # Sits just after the source once positions are renumbered.
                position=source.position * 2 + 1,
                extra=dict(source.extra),
            )
            self.repo.upsert_task(copy)
            created.append(next_id)
            next_id += 1

        # Space the originals out so the interleaved copies keep their slot.
        for task in self.repo.list_tasks():
            if task.id not in created:
                task.position = task.position * 2
                self.repo.upsert_task(task)

        self.normalise_positions()
        return created

    def delete(self, ids: Iterable[int]) -> int:
        """Delete tasks and return how many ids were requested."""
        ids = [int(i) for i in ids]
        self.repo.delete_tasks(ids)
        self.normalise_positions()
        return len(ids)

    def reorder(self, ordered_ids: list[int]) -> None:
        """Set positions to match the given order; unknown ids are skipped."""
        index = {task.id: task for task in self.repo.list_tasks()}
        for position, task_id in enumerate(ordered_ids):
            task = index.get(int(task_id))
            if task is None:
                continue
            task.position = position
            self.repo.upsert_task(task)

    def normalise_positions(self) -> None:
        """Renumber positions to a dense 0..n-1 sequence."""
        for position, task in enumerate(self.repo.list_tasks()):
            if task.position != position:
                task.position = position
                self.repo.upsert_task(task)

    # --------------------------------------------------------------- resets

    def apply_recurrence_resets(self, now: Optional[datetime] = None) -> int:
        """Run every recurrence rule whose window has rolled over.

        The boundary of the last completed window is recorded per rule, so a
        reset fires exactly once even if the application was closed across
        several windows.

        Returns:
            How many tasks were reset.
        """
        now = now or datetime.now(timezone.utc)
        target = self.settings.reset_status()
        changed = 0

        for key in self.recurrence.keys():
            boundary = self.recurrence.get(key).last_boundary(now)
            if boundary is None:
                continue

            marker_key = f"reset_marker:{key}"
            marker = boundary.isoformat()
            if self.repo.get_setting(marker_key) == marker:
                continue

            for task in self.repo.list_tasks():
                if task.recurrence != key or task.status == target:
                    continue
                task.status = target
                task.last_updated = today_iso()
                self.repo.upsert_task(task)
                changed += 1

            self.repo.set_setting(marker_key, marker)
        return changed
