from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

READY = "Ready"
BLOCKED = "Blocked"
INVALID_DEPENDENCY = "Invalid ID"
SELF_REFERENCE = "Self-reference"


@dataclass
class Task:
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
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Task":
        known = set(cls.__dataclass_fields__)
        payload = {k: v for k, v in raw.items() if k in known}
        payload["id"] = int(payload["id"])
        payload["dependencies"] = normalise_dependencies(
            raw.get("dependencies", raw.get("dependency"))
        )
        payload.setdefault("extra", {})
        return cls(**payload)


def normalise_dependencies(value: Any) -> list[int]:
    """Accept a list, a scalar, or the legacy single-dependency field."""
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
class Definition:
    kind: str
    value: str
    color: str = "#94a3b8"
    position: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PlannerError(Exception):
    """Domain error surfaced to the user as a 400 response."""
