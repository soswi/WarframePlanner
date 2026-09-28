"""The task record and the vocabulary used to describe its readiness."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

# States reported for a task's prerequisites. Not user-defined: unlike a status,
# these are computed from the dependency graph and the UI keys styling off them.
READY = "Ready"
BLOCKED = "Blocked"
INVALID_DEPENDENCY = "Invalid ID"
SELF_REFERENCE = "Self-reference"


def normalise_dependencies(value: Any) -> list[int]:
    """Coerce any accepted dependency shape into a list of unique ids.

    Accepts a list, a bare scalar, or the single-value ``dependency`` field used
    before schema v2, so imports of older files keep working.

    Args:
        value: Whatever the caller supplied for the dependency field.

    Returns:
        Task ids in the order first seen, without duplicates or blanks.
    """
    if value in (None, "", "None", []):
        return []
    if not isinstance(value, (list, tuple, set)):
        value = [value]

    out: list[int] = []
    for item in value:
        if item in (None, "", "None"):
            continue
        parsed = int(item)
        if parsed not in out:
            out.append(parsed)
    return out


@dataclass
class Task:
    """A single planner entry.

    ``position`` holds the display order rather than relying on id order, so
    tasks can be reordered without renumbering. ``extra`` is a free-form bag for
    data that does not warrant a schema change.
    """

    id: int
    activity: str = ""
    category: str = ""
    description: str = ""
    priority: str = ""
    status: str = ""
    dependencies: list[int] = field(default_factory=list)
    recurrence: str = "One-off"
    last_updated: Optional[str] = None
    position: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    #: Fields a client is allowed to change. Anything else in a patch is ignored
    #: rather than rejected, so a newer client cannot corrupt an older server.
    EDITABLE_FIELDS = (
        "activity",
        "category",
        "description",
        "priority",
        "status",
        "dependencies",
        "recurrence",
        "last_updated",
    )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable copy."""
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Task":
        """Build a task from untrusted input, such as an imported file.

        Unknown keys are dropped and the legacy ``dependency`` field is folded
        into ``dependencies``.

        Args:
            raw: Mapping holding at least an ``id``.

        Returns:
            A task with every field normalised.
        """
        known = set(cls.__dataclass_fields__)
        payload = {k: v for k, v in raw.items() if k in known}
        payload["id"] = int(payload["id"])
        payload["dependencies"] = normalise_dependencies(
            raw.get("dependencies", raw.get("dependency"))
        )
        payload.setdefault("extra", {})
        return cls(**payload)
