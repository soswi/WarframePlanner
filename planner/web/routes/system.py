"""Process-level endpoints: identification and shutdown."""

from __future__ import annotations

import os
from typing import Any, Callable, Optional

from fastapi import APIRouter

from ...models import PlannerError

#: Identifies our own server when probing a port an earlier instance claimed,
#: so the browser is never handed to an unrelated service.
APP_SIGNATURE = "warframe-planner"


def build_router(
    on_shutdown: Optional[Callable[[], None]] = None,
    environment: Optional[dict[str, Any]] = None,
) -> APIRouter:
    """Return the system routes.

    Args:
        on_shutdown: Called to stop the server. Absent in builds that embed the
            app without owning the process.
        environment: Description of the data environment, shown by the client.
    """
    router = APIRouter()
    described = environment or {"test": False, "label": ""}

    @router.get("/environment")
    def get_environment() -> dict[str, Any]:
        """Which data environment this instance runs against."""
        return described

    @router.get("/ping")
    def ping() -> dict[str, Any]:
        """Identify this process to another instance starting up."""
        return {"app": APP_SIGNATURE, "pid": os.getpid()}

    @router.post("/shutdown")
    def shutdown() -> dict[str, Any]:
        """Stop the whole process, not just this browser tab.

        The hook only sets a flag; the server finishes writing this response
        before it unwinds, so the browser still gets a clean answer.

        Raises:
            PlannerError: If this build has no shutdown hook.
        """
        if on_shutdown is None:
            raise PlannerError("This build has no shutdown hook installed.")
        on_shutdown()
        return {"stopping": True}

    return router
