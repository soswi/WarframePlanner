"""Ways of arranging tasks on screen. The frontend holds the matching renderer."""

from __future__ import annotations

from .base import Presentation, PresentationRegistry

DEFAULT_LAYOUT = "table"


class Layout(Presentation):
    """A way of arranging tasks on screen. The frontend holds the matching renderer."""


class TableLayout(Layout):
    key = "table"
    label = "Table"
    description = "Spreadsheet-style grid with sortable columns."


class BoardLayout(Layout):
    key = "board"
    label = "Board"
    description = "Grouped cards with drag-and-drop and inline status editing."


def default_layouts() -> PresentationRegistry:
    registry = PresentationRegistry(fallback=DEFAULT_LAYOUT)
    for layout in (TableLayout(), BoardLayout()):
        registry.register(layout)
    return registry


