"""Opt-in reference-layout mapping; never resamples a captured frame."""

import math


def anchored_point(x, y, width, height, reference_ratio, *, hcenter=False, vcenter=False):
    """Map normalized reference coordinates using uniform scale and UI anchors.

    Exact midpoints stay centered. Other points retain distance to their nearest
    edge unless the caller explicitly selects a center anchor.
    """
    if not all(math.isfinite(v) for v in (x, y, width, height, reference_ratio)):
        raise ValueError("layout geometry must be finite")
    if width <= 0 or height <= 0 or reference_ratio <= 0:
        raise ValueError("layout geometry must be positive")
    reference_width = height * reference_ratio
    scale = min(width / reference_width, 1.0)

    def axis(value, reference, actual, center):
        if center or math.isclose(value, 0.5, rel_tol=0.0, abs_tol=1e-12):
            return round(actual / 2 + (value - 0.5) * reference * scale)
        if value > 0.5:
            return round(actual - (1 - value) * reference * scale)
        return round(value * reference * scale)

    return (axis(x, reference_width, width, hcenter),
            axis(y, height, height, vcenter))


def anchored_box(x, y, to_x, to_y, box_width, box_height, width, height,
                 reference_ratio, *, hcenter=False, vcenter=False):
    """Endpoint ROIs span layout anchors; explicit sizes remain uniformly scaled."""
    left, top = anchored_point(x, y, width, height, reference_ratio,
                               hcenter=hcenter, vcenter=vcenter)
    right, bottom = anchored_point(to_x, to_y, width, height, reference_ratio,
                                   hcenter=hcenter, vcenter=vcenter)
    scale = min(width / (height * reference_ratio), 1.0)
    w = round(box_width * height * reference_ratio * scale) if box_width else right - left
    h = round(box_height * height * scale) if box_height else bottom - top
    if w < 0 or h < 0:
        raise ValueError("layout box dimensions must be nonnegative")
    return left, top, w, h
