"""Endpoints for exporting and importing the whole store."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response

from ...domain import PlannerService
from ...models import PlannerError


def build_router(service: PlannerService) -> APIRouter:
    """Return the export and import routes bound to ``service``."""
    router = APIRouter()

    @router.get("/export")
    def export_data() -> Response:
        """Download the whole store as a JSON attachment."""
        body = json.dumps(service.export_payload(), indent=2, ensure_ascii=False)
        filename = f"warframe-planner-{date.today().isoformat()}.json"
        return Response(
            content=body,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.post("/import")
    async def import_data(file: UploadFile = File(...), merge: bool = False) -> dict[str, Any]:
        """Load an exported file, replacing or merging.

        Raises:
            PlannerError: If the upload is not readable JSON.
        """
        raw = await file.read()
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PlannerError(f"Could not read the file: {exc}") from exc

        service.import_payload(payload, merge=merge)
        return service.snapshot()

    return router
