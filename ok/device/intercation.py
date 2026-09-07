"""Compatibility facade for the historical misspelled interaction module."""

from __future__ import annotations

from ok.device import interaction_methods as _interaction_methods


__all__ = list(_interaction_methods.__all__)


def __getattr__(name):
    value = getattr(_interaction_methods, name)
    globals()[name] = value
    return value
