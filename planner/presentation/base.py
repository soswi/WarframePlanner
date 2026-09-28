"""Catalogues of options the user picks from but cannot author.

Layouts and themes are defined in code: the store keeps only the selected key,
and the frontend owns the rendering. Adding one means adding a subclass and
registering it.
"""

from __future__ import annotations

from abc import ABC
from typing import Any


class Presentation(ABC):
    """Base for anything the user can switch between but not author.

    Both layouts and themes are catalogues of code-defined options: the backend
    stores only the selected key, the frontend owns the rendering. Adding an
    option means adding a subclass and registering it.
    """

    key: str = ""
    label: str = ""
    description: str = ""

    def describe(self) -> dict[str, Any]:
        return {"key": self.key, "label": self.label, "description": self.description}


class PresentationRegistry:
    """Ordered catalogue of Presentation subclasses keyed by `key`."""

    def __init__(self, fallback: str) -> None:
        self._items: dict[str, Presentation] = {}
        self._fallback = fallback

    def register(self, item: Presentation) -> None:
        self._items[item.key] = item

    def get(self, key: str) -> Presentation:
        return self._items.get(key) or self._items[self._fallback]

    def keys(self) -> list[str]:
        return list(self._items)

    def describe(self) -> list[dict[str, Any]]:
        return [item.describe() for item in self._items.values()]
