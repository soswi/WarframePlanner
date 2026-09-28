"""The storage contract every backend must satisfy."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Optional

from ..models import Definition, Task


class Repository(ABC):
    """Persistence boundary for the whole application.

    Only this interface is visible to the domain layer, so swapping SQLite for
    another backend means implementing these methods and changing one line of
    wiring in `planner.runtime.server`.
    """

    @abstractmethod
    def list_tasks(self) -> list[Task]:
        """Return every task ordered by position, then id."""

    @abstractmethod
    def upsert_task(self, task: Task) -> None:
        """Insert a task, or overwrite the existing row with the same id."""

    @abstractmethod
    def delete_tasks(self, ids: Iterable[int]) -> None:
        """Remove tasks and strip them from every remaining dependency list."""

    @abstractmethod
    def replace_tasks(self, tasks: Iterable[Task]) -> None:
        """Discard all tasks and store the given ones instead."""

    @abstractmethod
    def list_definitions(self) -> list[Definition]:
        """Return every definition ordered by kind, then position."""

    @abstractmethod
    def replace_definitions(self, kind: str, definitions: Iterable[Definition]) -> None:
        """Replace one kind wholesale; positions follow the given order."""

    @abstractmethod
    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Return a stored setting, or ``default`` when it is absent."""

    @abstractmethod
    def set_setting(self, key: str, value: str) -> None:
        """Store a setting, replacing any existing value."""

    @abstractmethod
    def all_settings(self) -> dict[str, str]:
        """Return every stored setting."""
