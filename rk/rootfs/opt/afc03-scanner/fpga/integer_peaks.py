"""Integer reference for the current 5-tap / scipy.find_peaks front end.

No floating-point arithmetic and no SciPy dependency. The default distance tie
rule is right-first, explicitly chosen by the user. NumPy's integer quicksort
is available only for runtime legacy comparison, not claimed portable.
Units: smooth16 = Gaussian numerator; base32 = twice its median.
"""
from dataclasses import dataclass
import numpy as np


@dataclass
class PeakResult:
    base32: int
    peaks: list[int]
    local_peaks: list[int]
    distance_peaks: list[int]
    prominence16: list[int]
    tie_conflicts: list[tuple[int, int, int]]


def median32(values):
    """Twice median, exactly including the half-integral even-length case."""
    ordered = sorted(int(v) for v in values)
    if not ordered:
        raise ValueError("empty ROI")
    n = len(ordered)
    return ordered[(n - 1) // 2] + ordered[n // 2]


def local_maxima(values):
    """Strict outside slopes, plateau midpoint rounded down, endpoints excluded."""
    peaks = []
    i = 1
    stop = len(values) - 1
    while i < stop:
        if values[i - 1] < values[i]:
            end = i + 1
            while end < stop and values[end] == values[i]:
                end += 1
            if values[end] < values[i]:
                peaks.append((i + end - 1) // 2)
            i = end
        else:
            i += 1
    return peaks


def distance_filter(values, peaks, distance=8, tie_policy="right"):
    """Descending height; right-first by default, optional legacy comparison.

    The legacy_numpy mode matched local SciPy 1.13.1 / NumPy 1.26.4 in regression;
    it is not a portable tie-order specification. The default right-first policy
    is intentionally an explicit, versioned algorithm decision.
    """
    if tie_policy == "right":
        order = sorted(range(len(peaks)), key=lambda i: (values[peaks[i]], peaks[i]))
    elif tie_policy == "legacy_numpy":
        priority = np.array([values[k] for k in peaks], dtype=np.int64)
        order = np.argsort(priority, kind="quicksort").tolist()
    else:
        raise ValueError("unknown tie policy")
    keep = [True] * len(peaks)
    for j in reversed(order):
        if not keep[j]:
            continue
        k = j - 1
        while k >= 0 and peaks[j] - peaks[k] < distance:
            keep[k] = False
            k -= 1
        k = j + 1
        while k < len(peaks) and peaks[k] - peaks[j] < distance:
            keep[k] = False
            k += 1
    return [k for k, yes in zip(peaks, keep) if yes]


def prominence(values, k):
    """Unbounded scipy prominence; equal-height peaks do not stop a search."""
    height = int(values[k])
    lm = rm = height
    i = k
    while i >= 0 and values[i] <= height:
        lm = min(lm, int(values[i]))
        i -= 1
    i = k
    while i < len(values) and values[i] <= height:
        rm = min(rm, int(values[i]))
        i += 1
    return height - max(lm, rm)


def detect(smooth16, left, right, *, distance=8, prominence16=288, tie_policy="right"):
    """Inclusive ROI; returns full row x coordinates. Distance precedes prominence."""
    if not 0 <= left < right < len(smooth16):
        raise ValueError("invalid inclusive ROI")
    if distance < 1 or prominence16 < 0:
        raise ValueError("invalid threshold")
    if np.asarray(smooth16).dtype.kind not in "ui":
        raise TypeError("integer smooth16 required")
    values = [int(v) for v in smooth16[left:right + 1]]
    if min(values) < 0 or max(values) > 4080:
        raise ValueError("smooth16 outside uint8 RGB Gaussian range")
    local = local_maxima(values)
    conflicts = []
    for i, k in enumerate(local):
        for j in local[i + 1:]:
            if j - k >= distance:
                break
            if values[j] == values[k]:
                conflicts.append((k + left, j + left, values[k]))
    separated = distance_filter(values, local, distance, tie_policy)
    prom = [prominence(values, k) for k in separated]
    selected = [k + left for k, p in zip(separated, prom) if p >= prominence16]
    return PeakResult(median32(values), selected, [k + left for k in local],
                      [k + left for k in separated], prom, conflicts)


def prepare(on, off, left, right, *, tie_policy="right"):
    """Drop-in integer prepare tuple plus detailed front-end diagnostics."""
    on = np.asarray(on)
    off = np.asarray(off)
    if on.dtype != np.uint8 or off.dtype != np.uint8 or on.shape != off.shape:
        raise ValueError("on/off must be equal uint8 RGB/BGR arrays")
    if on.ndim != 2 or on.shape[1] != 3 or len(on) < 3:
        raise ValueError("expected width by three channels")
    signal = np.maximum(on.astype(np.int16) - off.astype(np.int16), 0).max(1).astype(np.uint16)
    rawmax = on.max(1).astype(np.uint16)
    padded = np.pad(signal, (2, 2), mode="reflect")
    smooth = sum(w * padded[i:i + len(signal)] for i, w in enumerate((1, 4, 6, 4, 1)))
    result = detect(smooth, left, right, tie_policy=tie_policy)
    return signal, rawmax, smooth, result.base32, np.array(result.peaks, dtype=int), result
