"""Read and write the key-value settings that steer application behaviour."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import PlannerError
from ..storage import Repository

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters to type checkers
    from ..presentation import PresentationRegistry

DEFAULT_DONE_STATUS = "Done"
DEFAULT_RESET_STATUS = "In Progress"
DEFAULT_MIN_TASK_ID = 1000


class SettingsService:
    """Typed access to settings, plus validation of the ones that name a
    code-defined option.

    Settings are stored as strings because they come from and go back to a form.
    Every accessor here exists so the rest of the code never has to remember a
    key name or repeat a default.
    """

    def __init__(
        self,
        repo: Repository,
        layouts: "PresentationRegistry",
        themes: "PresentationRegistry",
    ) -> None:
        self.repo = repo
        self.layouts = layouts
        self.themes = themes

    def done_status(self) -> str:
        """Status that counts a task as finished."""
        return self.repo.get_setting("done_status", DEFAULT_DONE_STATUS) or DEFAULT_DONE_STATUS

    def reset_status(self) -> str:
        """Status a recurring task returns to when its window rolls over."""
        return (
            self.repo.get_setting("reset_status", DEFAULT_RESET_STATUS)
            or DEFAULT_RESET_STATUS
        )

    def highlight_status(self) -> str:
        """Status pinned to the front of every list; empty disables pinning."""
        return (self.repo.get_setting("highlight_status", "") or "").strip()

    def gate_enabled(self) -> bool:
        """Whether completing a task requires its dependencies to be done."""
        return (self.repo.get_setting("enforce_dependency_gate", "true") or "true") == "true"

    def min_task_id(self) -> int:
        """Lowest id a newly created task may take."""
        raw = self.repo.get_setting("min_task_id", str(DEFAULT_MIN_TASK_ID))
        try:
            return int(raw or DEFAULT_MIN_TASK_ID)
        except ValueError:
            # A hand-edited database should not stop the app from starting.
            return DEFAULT_MIN_TASK_ID

    def all(self) -> dict[str, str]:
        """Return every stored setting."""
        return self.repo.all_settings()

    def save(self, settings: dict[str, str]) -> None:
        """Store settings, rejecting unknown themes and layouts.

        Args:
            settings: Keys to write, values coerced to strings.

        Raises:
            PlannerError: If a theme or layout key names something unregistered.
        """
        for key, value in settings.items():
            value = str(value)
            if key == "theme" and value not in self.themes.keys():
                raise PlannerError(f"Unknown theme: {value}")
            if key == "layout" and value not in self.layouts.keys():
                raise PlannerError(f"Unknown layout: {value}")
            self.repo.set_setting(key, value)

    def coerced(self) -> dict[str, str]:
        """Return settings with any removed theme or layout repaired.

        An update can drop a theme that a database still names. Left alone the
        interface would render unstyled, so the value is rewritten to the
        registry's fallback and persisted.
        """
        settings = self.repo.all_settings()
        for key, registry in (("theme", self.themes), ("layout", self.layouts)):
            current = settings.get(key)
            if current not in registry.keys():
                resolved = registry.get(current or "").key
                self.repo.set_setting(key, resolved)
                settings[key] = resolved
        return settings
