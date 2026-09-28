"""Request bodies accepted by the API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class TaskUpdate(BaseModel):
    """A partial update. ``changes`` is required: an empty patch is a mistake."""

    changes: dict[str, Any]


class TaskCreate(BaseModel):
    """Creation, optionally with initial field values.

    Separate from `TaskUpdate` because creating without any values is normal,
    so ``changes`` defaults to empty rather than being required.
    """

    changes: dict[str, Any] = {}


class IdList(BaseModel):
    """A set of task ids to act on."""

    ids: list[int]


class DefinitionsPayload(BaseModel):
    """A whole definition kind, in display order."""

    kind: str
    entries: list[dict[str, Any]]


class SettingsPayload(BaseModel):
    """Settings to store, as submitted by a form."""

    settings: dict[str, str]
