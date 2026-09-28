"""The user-editable vocabularies: statuses, priorities and categories."""

from __future__ import annotations

from typing import Any

from ..defaults import DEFAULT_DEFINITIONS
from ..models import Definition, PlannerError
from ..storage import Repository

DEFAULT_COLOR = "#94a3b8"

#: Kinds that are defined in code and therefore cannot be edited as data.
CODE_DEFINED_KINDS = frozenset({"recurrence"})


class DefinitionService:
    """Grouped reads and whole-kind writes.

    A kind is always replaced in full rather than patched: order carries meaning
    and is taken from the submitted sequence, so a partial update would have no
    sensible way to place anything.
    """

    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def grouped(self) -> dict[str, list[dict[str, Any]]]:
        """Return definitions as ``{kind: [definition, ...]}`` in display order."""
        grouped: dict[str, list[dict[str, Any]]] = {}
        for definition in self.repo.list_definitions():
            grouped.setdefault(definition.kind, []).append(definition.to_dict())
        return grouped

    def save(self, kind: str, entries: list[dict[str, Any]]) -> None:
        """Replace one kind with the given entries.

        Blank and duplicate values are dropped rather than rejected, so a row
        left empty in the dialog simply disappears.

        Args:
            kind: Vocabulary to replace.
            entries: Mappings with ``value`` and optionally ``color``.

        Raises:
            PlannerError: If the kind is defined in code.
        """
        if kind in CODE_DEFINED_KINDS:
            raise PlannerError(f"{kind.capitalize()} is defined in code, not in data.")

        seen: set[str] = set()
        cleaned: list[Definition] = []
        for entry in entries:
            value = str(entry.get("value", "")).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            cleaned.append(
                Definition(kind=kind, value=value, color=entry.get("color") or DEFAULT_COLOR)
            )

        self.repo.replace_definitions(kind, cleaned)

    def save_many(self, definitions: dict[str, list[dict[str, Any]]]) -> None:
        """Replace several kinds, skipping any that are defined in code."""
        for kind, entries in (definitions or {}).items():
            if kind in CODE_DEFINED_KINDS:
                continue
            self.save(kind, entries)

    def reset_to_defaults(self) -> None:
        """Replace every editable kind with the shipped palette.

        Settings are left alone. One that names a value the defaults do not
        contain, such as a renamed completion status, keeps pointing at it.
        """
        for kind, values in DEFAULT_DEFINITIONS.items():
            self.repo.replace_definitions(
                kind,
                [Definition(kind=kind, value=value, color=color) for value, color in values],
            )

