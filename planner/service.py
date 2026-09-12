from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional

from .models import (
    BLOCKED,
    INVALID_DEPENDENCY,
    READY,
    SELF_REFERENCE,
    Definition,
    PlannerError,
    Task,
    normalise_dependencies,
)
from .presentation import PresentationRegistry, default_layouts, default_themes
from .recurrence import RecurrenceRegistry, default_registry
from .repository import Repository

EXPORT_SCHEMA_VERSION = 2


class PlannerService:
    """All business rules. Knows the Repository interface and nothing about HTTP."""

    def __init__(
        self,
        repo: Repository,
        recurrence: Optional[RecurrenceRegistry] = None,
        layouts: Optional[PresentationRegistry] = None,
        themes: Optional[PresentationRegistry] = None,
    ) -> None:
        self.repo = repo
        self.recurrence = recurrence or default_registry()
        self.layouts = layouts or default_layouts()
        self.themes = themes or default_themes()

    # ------------------------------------------------------------------ reads

    @staticmethod
    def _today() -> str:
        return date.today().isoformat()

    def done_status(self) -> str:
        return self.repo.get_setting("done_status", "Done") or "Done"

    def highlight_status(self) -> str:
        """Status pinned to the front of every list. Empty disables pinning."""
        return (self.repo.get_setting("highlight_status", "") or "").strip()

    def gate_enabled(self) -> bool:
        return (self.repo.get_setting("enforce_dependency_gate", "true") or "true") == "true"

    def resolve_prereq(self, task: Task, index: dict[int, Task]) -> dict[str, Any]:
        """Summarise a task's dependencies into a single status plus the blockers."""
        if not task.dependencies:
            return {"state": READY, "blocked_by": [], "missing": []}
        if task.id in task.dependencies:
            return {"state": SELF_REFERENCE, "blocked_by": [], "missing": []}

        missing = [d for d in task.dependencies if d not in index]
        if missing:
            return {"state": INVALID_DEPENDENCY, "blocked_by": [], "missing": missing}

        done = self.done_status()
        blocked_by = [d for d in task.dependencies if index[d].status != done]
        state = READY if not blocked_by else BLOCKED
        return {"state": state, "blocked_by": blocked_by, "missing": []}

    def list_tasks(self) -> list[dict[str, Any]]:
        tasks = self.repo.list_tasks()
        index = {t.id: t for t in tasks}
        highlight = self.highlight_status()
        out = []
        for task in tasks:
            payload = task.to_dict()
            resolved = self.resolve_prereq(task, index)
            payload["prereq_status"] = resolved["state"]
            payload["blocked_by"] = resolved["blocked_by"]
            payload["missing_dependencies"] = resolved["missing"]
            payload["highlighted"] = bool(highlight) and task.status == highlight
            out.append(payload)

        # Pinned tasks lead, everything else keeps its stored order. Sorting is
        # stable, so this is a partition rather than a reshuffle.
        out.sort(key=lambda payload: not payload["highlighted"])
        return out

    def definitions(self) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for definition in self.repo.list_definitions():
            grouped.setdefault(definition.kind, []).append(definition.to_dict())
        return grouped

    def stats(self) -> dict[str, Any]:
        tasks = self.repo.list_tasks()
        done_status = self.done_status()
        counts: dict[str, int] = {}
        for task in tasks:
            if task.status:
                counts[task.status] = counts.get(task.status, 0) + 1
        total = len(tasks)
        done = counts.get(done_status, 0)
        return {
            "total": total,
            "counts": counts,
            "done": done,
            "completion_rate": (done / total) if total else 0.0,
        }

    def coerce_settings(self) -> dict[str, str]:
        """Repair settings that name a theme or layout this build no longer has."""
        settings = self.repo.all_settings()
        for key, registry in (("theme", self.themes), ("layout", self.layouts)):
            current = settings.get(key)
            if current not in registry.keys():
                resolved = registry.get(current or "").key
                self.repo.set_setting(key, resolved)
                settings[key] = resolved
        return settings

    def snapshot(self) -> dict[str, Any]:
        return {
            "tasks": self.list_tasks(),
            "definitions": self.definitions(),
            "settings": self.coerce_settings(),
            "recurrence": self.recurrence.describe(),
            "layouts": self.layouts.describe(),
            "themes": self.themes.describe(),
            "stats": self.stats(),
        }

    # ----------------------------------------------------------------- writes

    def next_id(self) -> int:
        floor = int(self.repo.get_setting("min_task_id", "1000") or 1000)
        existing = [t.id for t in self.repo.list_tasks()]
        return max(existing + [floor - 1]) + 1

    def create_task(self, at_top: bool = True) -> dict[str, Any]:
        tasks = self.repo.list_tasks()
        task = Task(id=self.next_id(), recurrence="One-off")
        if at_top:
            task.position = (min(t.position for t in tasks) - 1) if tasks else 0
        else:
            task.position = (max(t.position for t in tasks) + 1) if tasks else 0
        self.repo.upsert_task(task)
        self._normalise_positions()
        return task.to_dict()

    def update_task(self, task_id: int, changes: dict[str, Any]) -> dict[str, Any]:
        index = {t.id: t for t in self.repo.list_tasks()}
        task = index.get(task_id)
        if task is None:
            raise PlannerError(f"Task {task_id} does not exist.")

        for key, value in changes.items():
            if key not in Task.EDITABLE_FIELDS:
                continue
            if key == "dependencies":
                task.dependencies = self._validate_dependencies(task, value, index)
            elif key == "status":
                if value != task.status:
                    self._assert_status_allowed(task, value, index)
                    task.status = value
                    task.last_updated = self._today()
            elif key == "recurrence":
                if value not in self.recurrence.keys():
                    raise PlannerError(f"Unknown recurrence: {value}")
                task.recurrence = value
            else:
                setattr(task, key, value)

        self.repo.upsert_task(task)
        return task.to_dict()

    def _validate_dependencies(
        self, task: Task, value: Any, index: dict[int, Task]
    ) -> list[int]:
        wanted = normalise_dependencies(value)
        for dep in wanted:
            if dep == task.id:
                raise PlannerError("A task cannot depend on itself.")
            if dep not in index:
                raise PlannerError(f"Task {dep} does not exist.")
        probe = dict(index)
        probe[task.id] = Task(**{**task.to_dict(), "dependencies": wanted})
        cycle = self._find_cycle(task.id, probe)
        if cycle:
            raise PlannerError("That dependency creates a cycle: " + " -> ".join(map(str, cycle)))
        return wanted

    @staticmethod
    def _find_cycle(start: int, index: dict[int, Task]) -> Optional[list[int]]:
        """Depth-first search returning the offending path, or None."""
        path: list[int] = []
        on_path: set[int] = set()
        visited: set[int] = set()

        def walk(node_id: int) -> Optional[list[int]]:
            if node_id in on_path:
                return path[path.index(node_id):] + [node_id]
            if node_id in visited:
                return None
            node = index.get(node_id)
            if node is None:
                return None
            visited.add(node_id)
            path.append(node_id)
            on_path.add(node_id)
            for dep in node.dependencies:
                found = walk(dep)
                if found:
                    return found
            path.pop()
            on_path.discard(node_id)
            return None

        return walk(start)

    def _assert_status_allowed(
        self, task: Task, new_status: str, index: dict[int, Task]
    ) -> None:
        """Reject completion while any prerequisite is still open."""
        if not self.gate_enabled() or new_status != self.done_status():
            return
        resolved = self.resolve_prereq(task, index)
        if resolved["missing"]:
            raise PlannerError(
                "Cannot complete: dependencies do not exist ("
                + ", ".join(map(str, resolved["missing"]))
                + ")."
            )
        if resolved["blocked_by"]:
            names = []
            for dep_id in resolved["blocked_by"]:
                dep = index[dep_id]
                label = dep.activity or f"Task {dep.id}"
                names.append(f"{dep.id} {label} [{dep.status or 'no status'}]")
            raise PlannerError(
                "Cannot mark as "
                + self.done_status()
                + " while these dependencies are open: "
                + "; ".join(names)
            )

    def duplicate_tasks(self, ids: Iterable[int]) -> list[int]:
        """Copy tasks, each landing directly below its source.

        Dependencies are kept as-is rather than remapped: a copy of "farm relics"
        still waits on the same prerequisite, which is almost always what is
        wanted. Status and Last Updated are cleared, because a copy has not been
        worked on yet.
        """
        index = {t.id: t for t in self.repo.list_tasks()}
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

        self._normalise_positions()
        return created

    def delete_tasks(self, ids: Iterable[int]) -> int:
        ids = [int(i) for i in ids]
        self.repo.delete_tasks(ids)
        self._normalise_positions()
        return len(ids)

    def reorder(self, ordered_ids: list[int]) -> None:
        index = {t.id: t for t in self.repo.list_tasks()}
        for position, task_id in enumerate(ordered_ids):
            task = index.get(int(task_id))
            if task is None:
                continue
            task.position = position
            self.repo.upsert_task(task)

    def _normalise_positions(self) -> None:
        for position, task in enumerate(self.repo.list_tasks()):
            if task.position != position:
                task.position = position
                self.repo.upsert_task(task)

    def save_definitions(self, kind: str, entries: list[dict[str, Any]]) -> None:
        if kind == "recurrence":
            raise PlannerError("Recurrence rules are defined in code, not in data.")
        seen: set[str] = set()
        cleaned: list[Definition] = []
        for entry in entries:
            value = str(entry.get("value", "")).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            cleaned.append(
                Definition(kind=kind, value=value, color=entry.get("color") or "#94a3b8")
            )
        self.repo.replace_definitions(kind, cleaned)

    def save_settings(self, settings: dict[str, str]) -> None:
        for key, value in settings.items():
            value = str(value)
            if key == "theme" and value not in self.themes.keys():
                raise PlannerError(f"Unknown theme: {value}")
            if key == "layout" and value not in self.layouts.keys():
                raise PlannerError(f"Unknown layout: {value}")
            self.repo.set_setting(key, value)

    # ---------------------------------------------------------------- resets

    def apply_recurrence_resets(self, now: Optional[datetime] = None) -> int:
        """Run every recurrence rule whose window has rolled over since last time."""
        now = now or datetime.now(timezone.utc)
        target = self.repo.get_setting("reset_status", "In Progress")
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
                task.last_updated = self._today()
                self.repo.upsert_task(task)
                changed += 1
            self.repo.set_setting(marker_key, marker)
        return changed

    # -------------------------------------------------------- export / import

    def export_payload(self) -> dict[str, Any]:
        return {
            "schema_version": EXPORT_SCHEMA_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "tasks": [t.to_dict() for t in self.repo.list_tasks()],
            "definitions": self.definitions(),
            "settings": self.repo.all_settings(),
        }

    def import_payload(self, payload: dict[str, Any], merge: bool = False) -> dict[str, int]:
        version = int(payload.get("schema_version", 0))
        if version > EXPORT_SCHEMA_VERSION:
            raise PlannerError(
                f"This file comes from a newer version of the app (schema {version})."
            )

        incoming = [Task.from_dict(raw) for raw in payload.get("tasks", [])]

        # Definitions are applied in both modes. A merge that silently dropped
        # them left no way to repair a damaged palette without replacing every
        # task as well.
        if merge:
            self._merge_tasks(incoming)
            for kind, entries in (payload.get("definitions") or {}).items():
                if kind != "recurrence":
                    self.save_definitions(kind, entries)
        else:
            self.repo.replace_tasks(incoming)
            for kind, entries in (payload.get("definitions") or {}).items():
                if kind == "recurrence":
                    continue
                self.save_definitions(kind, entries)
            settings = {
                k: v for k, v in (payload.get("settings") or {}).items()
                if not k.startswith("reset_marker:")
            }
            self.save_settings(settings)

        self._normalise_positions()
        return {"tasks": len(incoming)}

    def _merge_tasks(self, incoming: list[Task]) -> None:
        """Fold imported tasks into the existing set, updating rather than copying.

        A task is treated as the same task when it carries the same id, or
        failing that the same activity name. Only genuinely new tasks are
        inserted, and only they can be renumbered. Each existing task can absorb
        at most one incoming task, so a file containing two rows with the same
        name adds the second instead of overwriting the first twice.
        """
        existing = self.repo.list_tasks()
        by_id = {t.id: t for t in existing}
        by_name: dict[str, Task] = {}
        for task in existing:
            key = task.activity.strip().lower()
            if key:
                by_name.setdefault(key, task)

        taken = set(by_id)
        next_free = max(taken | {int(self.repo.get_setting("min_task_id", "1000") or 1000) - 1}) + 1

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
            task.dependencies = [remap.get(d, d) for d in task.dependencies]
            if position is not None:
                task.position = position
            self.repo.upsert_task(task)
