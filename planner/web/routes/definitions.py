"""Endpoints for the editable vocabularies and the settings that use them."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ...domain import PlannerService
from ..schemas import DefinitionsPayload, SettingsPayload


def build_router(service: PlannerService) -> APIRouter:
    """Return the definition and settings routes bound to ``service``."""
    router = APIRouter()

    @router.put("/definitions")
    def save_definitions(payload: DefinitionsPayload) -> dict[str, Any]:
        """Replace one definition kind."""
        service.save_definitions(payload.kind, payload.entries)
        return service.snapshot()

    @router.post("/definitions/reset")
    def reset_definitions() -> dict[str, Any]:
        """Restore every definition kind to the shipped palette."""
        service.reset_definitions()
        return service.snapshot()

    @router.put("/settings")
    def save_settings(payload: SettingsPayload) -> dict[str, Any]:
        """Store settings."""
        service.save_settings(payload.settings)
        return service.snapshot()

    return router
