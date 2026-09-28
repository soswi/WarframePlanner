"""Plain data types shared by every layer.

Nothing here reaches for storage, HTTP or configuration: these are records and
the rules for parsing them, and that is all.
"""

from .definition import Definition
from .errors import PlannerError
from .task import (
    BLOCKED,
    INVALID_DEPENDENCY,
    READY,
    SELF_REFERENCE,
    Task,
    normalise_dependencies,
)

__all__ = [
    "BLOCKED",
    "Definition",
    "INVALID_DEPENDENCY",
    "PlannerError",
    "READY",
    "SELF_REFERENCE",
    "Task",
    "normalise_dependencies",
]
