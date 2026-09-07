"""Structured, non-capture diagnostics for desktop window discovery."""

from __future__ import annotations

from ok.device.window_target.base import WindowCandidate


def candidate_diagnostics(candidate: WindowCandidate) -> dict[str, object]:
    return {
        "process_id": candidate.process_id,
        "bundle_identifier": candidate.bundle_identifier,
        "application_name": candidate.application_name,
        "window_id": candidate.window_id,
        "title": candidate.title,
        "layer": candidate.layer,
        "outer_geometry": candidate.outer_geometry.to_dict(),
        "content_geometry": (
            candidate.content_geometry.to_dict()
            if candidate.content_geometry is not None else None
        ),
        "capture_geometry": (
            candidate.capture_geometry.to_dict()
            if candidate.capture_geometry is not None else None
        ),
        "display_scale": candidate.display_scale,
        "frontmost": candidate.frontmost,
    }
