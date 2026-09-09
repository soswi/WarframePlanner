from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Optional

RESET_HOUR_UTC = 1


class RecurrenceRule(ABC):
    """A single recurrence policy.

    To add one (monthly, for example), subclass this and register it with
    RecurrenceRegistry.register(). Nothing else in the codebase needs to change:
    the UI reads the available rules from /api/state.
    """

    key: str = ""
    label: str = ""

    @abstractmethod
    def last_boundary(self, now: datetime) -> Optional[datetime]:
        """Most recent reset instant at or before `now`, or None if never resets."""


class OneOffRule(RecurrenceRule):
    key = "One-off"
    label = "Never resets"

    def last_boundary(self, now: datetime) -> Optional[datetime]:
        return None


class DailyRule(RecurrenceRule):
    key = "Daily"
    label = "Every day at 01:00 UTC"

    def last_boundary(self, now: datetime) -> Optional[datetime]:
        now = now.astimezone(timezone.utc)
        anchor = now.replace(hour=RESET_HOUR_UTC, minute=0, second=0, microsecond=0)
        if anchor > now:
            anchor -= timedelta(days=1)
        return anchor


class WeeklyRule(RecurrenceRule):
    key = "Weekly"
    label = "Mondays at 01:00 UTC"

    def last_boundary(self, now: datetime) -> Optional[datetime]:
        now = now.astimezone(timezone.utc)
        anchor = now.replace(hour=RESET_HOUR_UTC, minute=0, second=0, microsecond=0)
        anchor -= timedelta(days=anchor.weekday())
        if anchor > now:
            anchor -= timedelta(days=7)
        return anchor


class RecurrenceRegistry:
    def __init__(self) -> None:
        self._rules: dict[str, RecurrenceRule] = {}

    def register(self, rule: RecurrenceRule) -> None:
        self._rules[rule.key] = rule

    def get(self, key: str) -> RecurrenceRule:
        return self._rules.get(key, self._rules["One-off"])

    def keys(self) -> list[str]:
        return list(self._rules)

    def describe(self) -> list[dict[str, str]]:
        return [{"key": r.key, "label": r.label} for r in self._rules.values()]


def default_registry() -> RecurrenceRegistry:
    registry = RecurrenceRegistry()
    for rule in (OneOffRule(), DailyRule(), WeeklyRule()):
        registry.register(rule)
    return registry
