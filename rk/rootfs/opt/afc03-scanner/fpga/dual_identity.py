"""Conservative, row-local A/B association with explicit unknown results.

Geometry alone may allow both planes. A prior must come from labelled single
laser images or a previously accepted track; never from image left/right order.
No hardware access. This prototype is not installed in the scanner service.
"""
from itertools import product
import numpy as np


def assign_row(xs, valid_labels, priors=None, gate_px=8.0, margin_px=2.0):
    """Solve one-to-one association; abstain on close alternative hypotheses.

Inputs are independently extracted peaks. With a prior, cost is pixel motion;
an unmatched peak costs gate_px. Without a prior, only geometric uniqueness
can establish identity. Multiple plausible labels yield unknown.
"""
    xs = list(xs)
    assert len(xs) == len(valid_labels)
    assert len(xs) <= 2
    assert gate_px > margin_px >= 0
    options, costs = [], []
    for x, valid in zip(xs, valid_labels):
        c = {None: gate_px}
        for label in ('A', 'B'):
            if label not in valid:
                continue
            if priors is None:
                c[label] = 0.0
            elif label in priors and abs(x - priors[label]) < gate_px:
                c[label] = abs(x - priors[label])
        options.append(list(c))
        costs.append(c)
    hypotheses = []
    for labels in product(*options):
        known = [k for k in labels if k is not None]
        if len(set(known)) != len(known):
            continue
        hypotheses.append((sum(c[k] for c, k in zip(costs, labels)), labels))
    hypotheses.sort(key=lambda h: h[0])
    best_cost, best = hypotheses[0]
    result = []
    for i, (x, label) in enumerate(zip(xs, best)):
        alternative = min((score for score, labels in hypotheses if labels[i] != label), default=float('inf'))
        gap = alternative - best_cost
        accepted = label is not None and gap >= margin_px
        result.append(dict(x=float(x), label=label if accepted else None,
                           reason='accepted' if accepted else 'ambiguous_or_no_valid_prior',
                           alternative_cost_margin_px=float(gap) if np.isfinite(gap) else None))
    return result


def geometry_candidates(uv, camera, planes, axis, max_radius_mm=90):
    """Return both reconstructions; broad bounds are sanity checks, not identity."""
    import cv2
    uv = np.asarray(uv, float).reshape(-1, 2)
    if not len(uv):
        return [], {}
    rays = np.c_[cv2.undistortPoints(uv[:, None], np.array(camera['camera_matrix']),
                                   np.array(camera['distortion_coefficients'])).reshape(-1, 2), np.ones(len(uv))]
    direction = np.array(axis['axis_direction_for_positive_pulses_camera'], float)
    direction /= np.linalg.norm(direction)
    center = np.array(axis['axis_point_closest_to_camera_origin_mm'])
    candidates = [set() for _ in uv]
    xyz_by_label = {}
    for label in ('A', 'B'):
        plane = planes['laser_' + label]
        denom = rays @ np.array(plane['normal_camera'])
        safe = denom > .05
        xyz = np.full((len(uv), 3), np.nan)
        xyz[safe] = rays[safe] * (plane['offset_mm_n_dot_X_equals_offset'] / denom[safe])[:, None]
        delta = xyz - center
        radius = np.linalg.norm(delta - (delta @ direction)[:, None] * direction, axis=1)
        valid = safe & np.isfinite(xyz).all(1) & (xyz[:, 2] > 80) & (xyz[:, 2] < 350) & ((radius < max_radius_mm) if max_radius_mm is not None else np.ones(len(radius),bool))
        for i in np.flatnonzero(valid):
            candidates[i].add(label)
        xyz_by_label[label] = xyz
    return candidates, xyz_by_label
