"""User-defined vocabulary: the values a status, priority or category can take."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class Definition:
    """One selectable value within a `kind`, together with its colour.

    Attributes:
        kind: Which vocabulary this belongs to, e.g. ``status``.
        value: The label stored on tasks; matching is by exact string.
        color: Hex colour used wherever the value is shown.
        position: Display order within the kind, ascending.
    """

    kind: str
    value: str
    color: str = "#94a3b8"
    position: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable copy."""
        return asdict(self)
