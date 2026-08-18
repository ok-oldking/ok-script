"""Compatibility export for the framework-neutral application event bus."""

from ok.core.events import EventBus as Communicate
from ok.core.events import communicate

__all__ = ["Communicate", "communicate"]
