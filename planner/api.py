from __future__ import annotations

import json
import os
from datetime import date
from typing import Any, Callable, Optional

from fastapi import APIRouter, FastAPI, File, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import APP_TITLE, static_dir
from .models import PlannerError
from .service import PlannerService


class TaskUpdate(BaseModel):
    changes: dict[str, Any]


class TaskCreate(BaseModel):
    """Separate from TaskUpdate: creating without any initial values is normal,
    so `changes` defaults to empty rather than being required."""

    changes: dict[str, Any] = {}


class IdList(BaseModel):
    ids: list[int]


class DefinitionsPayload(BaseModel):
    kind: str
    entries: list[dict[str, Any]]


class SettingsPayload(BaseModel):
    settings: dict[str, str]


# Identifies our own server when probing a port an earlier instance claimed,
# so we never attach the browser to some unrelated service.
APP_SIGNATURE = "warframe-planner"


def build_router(service: PlannerService,
                 on_shutdown: Optional[Callable[[], None]] = None) -> APIRouter:
    """Thin transport layer. Every endpoint returns the full snapshot so the
    frontend never has to reconcile partial state."""
    router = APIRouter(prefix="/api")

    @router.get("/ping")
    def ping() -> dict[str, Any]:
        return {"app": APP_SIGNATURE, "pid": os.getpid()}

    @router.post("/shutdown")
    def shutdown() -> dict[str, Any]:
        """Stop the whole process, not just this tab.

        The hook only flips a flag; uvicorn finishes writing this response
        before it unwinds, so the browser still gets a clean answer.
        """
        if on_shutdown is None:
            raise PlannerError("This build has no shutdown hook installed.")
        on_shutdown()
        return {"stopping": True}

    @router.get("/state")
    def state() -> dict[str, Any]:
        service.apply_recurrence_resets()
        return service.snapshot()

    @router.post("/tasks")
    def create_task(at_top: bool = True,
                    payload: Optional[TaskCreate] = None) -> dict[str, Any]:
        """Create a task, optionally with its first field values already set.

        Accepting them here keeps 'add into this group' to a single round trip,
        so the client repaints once instead of twice.
        """
        created = service.create_task(at_top=at_top)
        if payload and payload.changes:
            service.update_task(created["id"], payload.changes)
        return service.snapshot()

    @router.patch("/tasks/{task_id}")
    def update_task(task_id: int, payload: TaskUpdate) -> dict[str, Any]:
        service.update_task(task_id, payload.changes)
        return service.snapshot()

    @router.post("/tasks/delete")
    def delete_tasks(payload: IdList) -> dict[str, Any]:
        service.delete_tasks(payload.ids)
        return service.snapshot()

    @router.post("/tasks/duplicate")
    def duplicate_tasks(payload: IdList) -> dict[str, Any]:
        service.duplicate_tasks(payload.ids)
        return service.snapshot()

    @router.post("/tasks/reorder")
    def reorder(payload: IdList) -> dict[str, Any]:
        service.reorder(payload.ids)
        return service.snapshot()

    @router.put("/definitions")
    def save_definitions(payload: DefinitionsPayload) -> dict[str, Any]:
        service.save_definitions(payload.kind, payload.entries)
        return service.snapshot()

    @router.put("/settings")
    def save_settings(payload: SettingsPayload) -> dict[str, Any]:
        service.save_settings(payload.settings)
        return service.snapshot()

    @router.get("/export")
    def export_data() -> Response:
        body = json.dumps(service.export_payload(), indent=2, ensure_ascii=False)
        filename = f"warframe-planner-{date.today().isoformat()}.json"
        return Response(
            content=body,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.post("/import")
    async def import_data(file: UploadFile = File(...), merge: bool = False) -> dict[str, Any]:
        raw = await file.read()
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PlannerError(f"Could not read the file: {exc}") from exc
        service.import_payload(payload, merge=merge)
        return service.snapshot()

    return router


def create_app(service: PlannerService,
               on_shutdown: Optional[Callable[[], None]] = None) -> FastAPI:
    app = FastAPI(title=APP_TITLE, docs_url=None, redoc_url=None)

    @app.exception_handler(PlannerError)
    async def planner_error_handler(_: Request, exc: PlannerError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    app.include_router(build_router(service, on_shutdown))
    root = static_dir()

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(root / "index.html")

    app.mount("/static", StaticFiles(directory=str(root)), name="static")
    return app
