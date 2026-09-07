"""Deterministic window matching and explicit manual-selection fallback."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import re
from typing import Iterable, Mapping

from ok.device.window_target.base import StableWindowHint, WindowCandidate


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, (list, tuple)):
        values = tuple(value)
    else:
        raise TypeError(f"{field_name} must be a string or sequence of strings")
    normalized = []
    for item in values:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} entries must be strings")
        if stripped := item.strip():
            normalized.append(stripped)
    return tuple(normalized)


@dataclass(frozen=True)
class WindowMatchHints:
    bundle_identifiers: tuple[str, ...] = ()
    application_names: tuple[str, ...] = ()
    title_patterns: tuple[str, ...] = ()
    allowed_layers: tuple[int, ...] = (0,)
    minimum_width: float = 0
    minimum_height: float = 0

    _ALLOWED_KEYS = frozenset({
        "bundle_identifiers", "application_names", "title_patterns",
        "allowed_layers", "minimum_width", "minimum_height",
    })

    def __post_init__(self) -> None:
        if not all(math.isfinite(value) for value in (
                self.minimum_width, self.minimum_height)):
            raise ValueError("minimum window dimensions must be finite")
        if self.minimum_width < 0 or self.minimum_height < 0:
            raise ValueError("minimum window dimensions must be non-negative")
        for pattern in self.title_patterns:
            try:
                re.compile(pattern)
            except re.error as error:
                raise ValueError(f"invalid title pattern {pattern!r}: {error}") from error

    @classmethod
    def from_mapping(cls, value: Mapping[str, object] | None) -> "WindowMatchHints":
        value = value or {}
        if not isinstance(value, Mapping):
            raise TypeError("window match hints must be a mapping")
        unknown = sorted(set(value) - cls._ALLOWED_KEYS)
        if unknown:
            raise ValueError("unknown window match hint fields: " + ", ".join(unknown))
        allowed_layers_value = value.get("allowed_layers", (0,))
        if isinstance(allowed_layers_value, int):
            allowed_layers: tuple[int, ...] = (allowed_layers_value,)
        elif isinstance(allowed_layers_value, (list, tuple)):
            allowed_layers = tuple(int(item) for item in allowed_layers_value)
        else:
            raise TypeError("allowed_layers must be an integer or sequence of integers")
        minimum_width = value.get("minimum_width", 0)
        minimum_height = value.get("minimum_height", 0)
        if (not isinstance(minimum_width, (int, float))
                or isinstance(minimum_width, bool)):
            raise TypeError("minimum_width must be a number")
        if (not isinstance(minimum_height, (int, float))
                or isinstance(minimum_height, bool)):
            raise TypeError("minimum_height must be a number")
        return cls(
            bundle_identifiers=_string_tuple(
                value.get("bundle_identifiers"), "bundle_identifiers"),
            application_names=_string_tuple(
                value.get("application_names"), "application_names"),
            title_patterns=_string_tuple(value.get("title_patterns"), "title_patterns"),
            allowed_layers=allowed_layers,
            minimum_width=float(minimum_width),
            minimum_height=float(minimum_height),
        )


class WindowSelectionStatus(str, Enum):
    SELECTED = "selected"
    MANUAL_SELECTION_REQUIRED = "manual-selection-required"
    NOT_FOUND = "not-found"


@dataclass(frozen=True)
class WindowSelectionResult:
    status: WindowSelectionStatus
    candidates: tuple[WindowCandidate, ...]
    selected: WindowCandidate | None = None

    @property
    def stable_hint(self) -> StableWindowHint:
        return self.selected.stable_hint() if self.selected else StableWindowHint()


def _casefold(value: str | None) -> str:
    return (value or "").strip().casefold()


def _eligible(candidate: WindowCandidate, hints: WindowMatchHints) -> bool:
    geometry = candidate.outer_geometry
    return (
        candidate.layer in hints.allowed_layers
        and geometry.width >= hints.minimum_width
        and geometry.height >= hints.minimum_height
        and candidate.process_id > 0
        and candidate.window_id > 0
    )


def _matches_stable_application_identity(
        candidate: WindowCandidate, hint: StableWindowHint) -> bool:
    if hint.bundle_identifier:
        return (
            _casefold(candidate.bundle_identifier)
            == _casefold(hint.bundle_identifier)
        )
    if hint.application_name:
        return (
            _casefold(candidate.application_name)
            == _casefold(hint.application_name)
        )
    return False


def _hint_matches(
        candidate: WindowCandidate, hints: WindowMatchHints) -> tuple[bool, bool]:
    bundle_match = _casefold(candidate.bundle_identifier) in {
        _casefold(value) for value in hints.bundle_identifiers
    }
    application_match = _casefold(candidate.application_name) in {
        _casefold(value) for value in hints.application_names
    }
    title_match = any(
        re.search(pattern, candidate.title, flags=re.IGNORECASE)
        for pattern in hints.title_patterns
    )

    if hints.bundle_identifiers:
        identity_match = bundle_match
    elif hints.application_names:
        identity_match = application_match
    else:
        identity_match = False
    return identity_match or title_match, identity_match


def select_window_candidate(
        candidates: Iterable[WindowCandidate],
        hints: WindowMatchHints,
        *,
        stable_hint: StableWindowHint | None = None,
        manual_window_id: int | None = None) -> WindowSelectionResult:
    """Select only when identity is unambiguous or the user chose a window.

    A title-only match is never enough for automatic selection.  When no stable
    identity matches, all otherwise eligible windows remain available for an
    explicit manual choice.
    """
    eligible = tuple(candidate for candidate in candidates if _eligible(candidate, hints))
    if not eligible:
        return WindowSelectionResult(WindowSelectionStatus.NOT_FOUND, ())

    if manual_window_id is not None:
        selected = next(
            (candidate for candidate in eligible
             if candidate.window_id == manual_window_id),
            None,
        )
        if selected is not None:
            return WindowSelectionResult(
                WindowSelectionStatus.SELECTED, eligible, selected)
        return WindowSelectionResult(
            WindowSelectionStatus.MANUAL_SELECTION_REQUIRED, eligible)

    stable_hint = stable_hint or StableWindowHint()
    if stable_hint.has_application_identity:
        stable_matches = tuple(
            candidate for candidate in eligible
            if _matches_stable_application_identity(candidate, stable_hint)
        )
        # Window titles are auxiliary and may change across launch/rebind.  Use
        # an exact persisted title only to disambiguate multiple windows owned
        # by the same application identity.
        if len(stable_matches) > 1 and stable_hint.title:
            title_matches = tuple(
                candidate for candidate in stable_matches
                if _casefold(candidate.title) == _casefold(stable_hint.title)
            )
            if len(title_matches) == 1:
                stable_matches = title_matches
        if len(stable_matches) == 1:
            return WindowSelectionResult(
                WindowSelectionStatus.SELECTED, stable_matches, stable_matches[0])
        if len(stable_matches) > 1:
            return WindowSelectionResult(
                WindowSelectionStatus.MANUAL_SELECTION_REQUIRED, stable_matches)

    hinted: list[WindowCandidate] = []
    identity_matches: list[WindowCandidate] = []
    for candidate in eligible:
        matched, identity_match = _hint_matches(candidate, hints)
        if matched:
            hinted.append(candidate)
        if identity_match:
            identity_matches.append(candidate)

    if len(identity_matches) == 1:
        selected = identity_matches[0]
        return WindowSelectionResult(
            WindowSelectionStatus.SELECTED, tuple(hinted), selected)

    manual_candidates = tuple(hinted) if hinted else eligible
    return WindowSelectionResult(
        WindowSelectionStatus.MANUAL_SELECTION_REQUIRED, manual_candidates)
