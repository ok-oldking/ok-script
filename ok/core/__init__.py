"""UI-independent application services and automation logic."""

from ok.core.events import EventBus, EventSignal, communicate

__all__ = ["EventBus", "EventSignal", "communicate"]
