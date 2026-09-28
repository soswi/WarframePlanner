"""Everything about running as a desktop process rather than a library."""

from .server import build_service, main

__all__ = ["build_service", "main"]
