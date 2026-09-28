"""Endpoints that read and change tasks."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter

from ...domain import PlannerService
from ..schemas import IdList, TaskCreate, TaskUpdate


def build_router(service: PlannerService) -> APIRouter:
    """Return the task routes bound to ``service``."""
    router = APIRouter()

    @router.get("/state")
    def state() -> dict[str, Any]:
        """Full client state, resetting any recurrence window that has passed."""
        service.apply_recurrence_resets()
        return service.snapshot()

    @router.post("/tasks")
    def create_task(at_top: bool = True,
                    payload: Optional[TaskCreate] = None) -> dict[str, Any]:
        """Create a task, optionally with its first field values already set.

        Accepting them here keeps "add into this group" to a single round trip,
        so the client repaints once instead of twice.
        """
        created = service.create_task(at_top=at_top)
        if payload and payload.changes:
            service.update_task(created["id"], payload.changes)
        return service.snapshot()

    @router.patch("/tasks/{task_id}")
    def update_task(task_id: int, payload: TaskUpdate) -> dict[str, Any]:
        """Apply a partial update to one task."""
        service.update_task(task_id, payload.changes)
        return service.snapshot()

    @router.post("/tasks/delete")
    def delete_tasks(payload: IdList) -> dict[str, Any]:
        """Delete the given tasks."""
        service.delete_tasks(payload.ids)
        return service.snapshot()

    @router.post("/tasks/duplicate")
    def duplicate_tasks(payload: IdList) -> dict[str, Any]:
        """Copy the given tasks, each landing below its source."""
        service.duplicate_tasks(payload.ids)
        return service.snapshot()

    @router.post("/tasks/reorder")
    def reorder(payload: IdList) -> dict[str, Any]:
        """Set task order to the given sequence of ids."""
        service.reorder(payload.ids)
        return service.snapshot()

    return router
