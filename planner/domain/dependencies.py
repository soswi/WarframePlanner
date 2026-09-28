"""Rules governing the dependency graph between tasks."""

from __future__ import annotations

from typing import Any, Optional

from ..models import (
    BLOCKED,
    INVALID_DEPENDENCY,
    READY,
    SELF_REFERENCE,
    PlannerError,
    Task,
    normalise_dependencies,
)
from .settings import SettingsService


class DependencyResolver:
    """Answers what a task is waiting on, and refuses edits that break the graph.

    Works on an in-memory index rather than reaching for storage, so a caller
    can evaluate a hypothetical change before committing it.
    """

    def __init__(self, settings: SettingsService) -> None:
        self.settings = settings

    def resolve(self, task: Task, index: dict[int, Task]) -> dict[str, Any]:
        """Summarise a task's prerequisites.

        Args:
            task: Task to evaluate.
            index: Every task, keyed by id.

        Returns:
            Mapping with ``state`` (one of the module-level constants),
            ``blocked_by`` (ids that exist but are unfinished) and ``missing``
            (ids that no longer exist).
        """
        if not task.dependencies:
            return {"state": READY, "blocked_by": [], "missing": []}
        if task.id in task.dependencies:
            return {"state": SELF_REFERENCE, "blocked_by": [], "missing": []}

        missing = [dep for dep in task.dependencies if dep not in index]
        if missing:
            return {"state": INVALID_DEPENDENCY, "blocked_by": [], "missing": missing}

        done = self.settings.done_status()
        blocked_by = [dep for dep in task.dependencies if index[dep].status != done]
        return {
            "state": READY if not blocked_by else BLOCKED,
            "blocked_by": blocked_by,
            "missing": [],
        }

    def validate(self, task: Task, value: Any, index: dict[int, Task]) -> list[int]:
        """Normalise and check a proposed dependency list.

        Args:
            task: Task the list will belong to.
            value: Raw value from the client.
            index: Every task, keyed by id.

        Returns:
            The accepted dependency ids.

        Raises:
            PlannerError: On self-reference, an unknown id, or a cycle.
        """
        wanted = normalise_dependencies(value)
        for dep in wanted:
            if dep == task.id:
                raise PlannerError("A task cannot depend on itself.")
            if dep not in index:
                raise PlannerError(f"Task {dep} does not exist.")

        # Evaluate the change against a copy, so a rejected edit leaves nothing
        # half-applied.
        probe = dict(index)
        probe[task.id] = Task(**{**task.to_dict(), "dependencies": wanted})
        cycle = self.find_cycle(task.id, probe)
        if cycle:
            raise PlannerError(
                "That dependency creates a cycle: " + " -> ".join(map(str, cycle))
            )
        return wanted

    @staticmethod
    def find_cycle(start: int, index: dict[int, Task]) -> Optional[list[int]]:
        """Depth-first search for a cycle reachable from ``start``.

        Returns:
            The offending path including the repeated node, or None.
        """
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

    def assert_status_allowed(
        self, task: Task, new_status: str, index: dict[int, Task]
    ) -> None:
        """Refuse completion while a prerequisite is still open.

        Does nothing unless the gate is enabled and the new status is the
        completion status.

        Raises:
            PlannerError: Naming the tasks that stand in the way.
        """
        if not self.settings.gate_enabled() or new_status != self.settings.done_status():
            return

        resolved = self.resolve(task, index)
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
                + self.settings.done_status()
                + " while these dependencies are open: "
                + "; ".join(names)
            )
