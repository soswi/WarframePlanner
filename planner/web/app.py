"""Assembles the FastAPI application from its routers and static files."""

from __future__ import annotations

from typing import Callable, Optional

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..config import APP_TITLE, static_dir
from ..domain import PlannerService
from ..models import PlannerError
from .routes import definitions, system, tasks, transfer

API_PREFIX = "/api"


def build_api_router(
    service: PlannerService,
    on_shutdown: Optional[Callable[[], None]] = None,
) -> APIRouter:
    """Combine every area router under the API prefix.

    Each endpoint returns the full snapshot, so the client never has to
    reconcile a partial update against what it already holds.
    """
    router = APIRouter(prefix=API_PREFIX)
    router.include_router(system.build_router(on_shutdown))
    router.include_router(tasks.build_router(service))
    router.include_router(definitions.build_router(service))
    router.include_router(transfer.build_router(service))
    return router


def create_app(
    service: PlannerService,
    on_shutdown: Optional[Callable[[], None]] = None,
) -> FastAPI:
    """Build the application.

    Args:
        service: Domain facade every route delegates to.
        on_shutdown: Callable that stops the process, wired by the runtime.
    """
    app = FastAPI(title=APP_TITLE, docs_url=None, redoc_url=None)

    @app.exception_handler(PlannerError)
    async def planner_error_handler(_: Request, exc: PlannerError) -> JSONResponse:
        """Surface a broken rule as a 400 with the message shown verbatim."""
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    app.include_router(build_api_router(service, on_shutdown))
    root = static_dir()

    @app.get("/")
    def index() -> FileResponse:
        """Serve the single page."""
        return FileResponse(root / "index.html")

    app.mount("/static", StaticFiles(directory=str(root)), name="static")
    return app
