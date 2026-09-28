"""Domain-level exceptions."""

from __future__ import annotations


class PlannerError(Exception):
    """A rule the caller broke, phrased for the person who broke it.

    The web layer turns this into a 400 with the message shown verbatim, so the
    text must always be safe and useful to show a user.
    """
