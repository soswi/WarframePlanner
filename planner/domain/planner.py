"""The facade the transport layer talks to."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Optional

from ..presentation import PresentationRegistry, default_layouts, default_themes
from ..storage import Repository
from .definitions import DefinitionService
from .dependencies import DependencyResolver
from .recurrence import RecurrenceRegistry, default_registry
from .settings import SettingsService
from .tasks import TaskService
from .transfer import TransferService


class PlannerService:
    """Composes the domain services and exposes them as one surface.

    Routes and tests depend on this rather than on the individual services, so
    the internal split can change without touching either. Each method here is
    a delegation; behaviour lives in the service that owns it.
    """

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

        self.settings = SettingsService(repo, self.layouts, self.themes)
        self.dependencies = DependencyResolver(self.settings)
        self.tasks = TaskService(repo, self.settings, self.dependencies, self.recurrence)
        self.definitions_service = DefinitionService(repo)
        self.transfer = TransferService(
            repo, self.tasks, self.definitions_service, self.settings
        )

    # ------------------------------------------------------------------ reads

    def list_tasks(self) -> list[dict[str, Any]]:
        """Every task, enriched and ordered for display."""
        return self.tasks.list()

    def definitions(self) -> dict[str, list[dict[str, Any]]]:
        """Definitions grouped by kind."""
        return self.definitions_service.grouped()

    def stats(self) -> dict[str, Any]:
        """Counts per status plus the completion ratio."""
        return self.tasks.stats()

    def coerce_settings(self) -> dict[str, str]:
        """Settings, with any removed theme or layout repaired."""
        return self.settings.coerced()

    def snapshot(self) -> dict[str, Any]:
        """The complete client state.

        Every mutating endpoint returns this, so the client never has to
        reconcile a partial update against what it already holds.
        """
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
        """Lowest unused task id."""
        return self.tasks.next_id()

    def create_task(self, at_top: bool = True) -> dict[str, Any]:
        """Create an empty task."""
        return self.tasks.create(at_top=at_top)

    def update_task(self, task_id: int, changes: dict[str, Any]) -> dict[str, Any]:
        """Apply a partial update to one task."""
        return self.tasks.update(task_id, changes)

    def duplicate_tasks(self, ids: Iterable[int]) -> list[int]:
        """Copy tasks, each landing below its source."""
        return self.tasks.duplicate(ids)

    def delete_tasks(self, ids: Iterable[int]) -> int:
        """Delete tasks by id."""
        return self.tasks.delete(ids)

    def reorder(self, ordered_ids: list[int]) -> None:
        """Set task order."""
        self.tasks.reorder(ordered_ids)

    def save_definitions(self, kind: str, entries: list[dict[str, Any]]) -> None:
        """Replace one definition kind."""
        self.definitions_service.save(kind, entries)

    def save_settings(self, settings: dict[str, str]) -> None:
        """Store settings after validating theme and layout keys."""
        self.settings.save(settings)

    def apply_recurrence_resets(self, now: Optional[datetime] = None) -> int:
        """Run any recurrence window that has rolled over."""
        return self.tasks.apply_recurrence_resets(now)

    # -------------------------------------------------------- export / import

    def export_payload(self) -> dict[str, Any]:
        """Full contents of the store, ready to serialise."""
        return self.transfer.export()

    def import_payload(self, payload: dict[str, Any], merge: bool = False) -> dict[str, int]:
        """Load an exported payload, replacing or merging."""
        return self.transfer.import_payload(payload, merge=merge)
