"""Demo-only exact ABI6 acceleration; canonical benchmark remains unchanged.

OpenCV saturated subtraction equals max(on-off, 0) for uint8. Channel-wise
max avoids the strided NumPy three-channel reduction. Peak suppression retains
canonical descending (height, coordinate) order, including rightmost ties.
"""
import cv2
import numpy as np
from scipy.signal import find_peaks, peak_prominences
from candidates import SETTINGS, evaluate, core


def _max_channel(image):
    a, b, c = cv2.split(image)
    return cv2.max(cv2.max(a, b), c)


def _suppress(peaks, values, distance):
    coordinates = peaks.tolist()
    heights = values[peaks].tolist()
    alive = bytearray([1]) * len(coordinates)
    for j in sorted(range(len(coordinates)), key=lambda i: (heights[i], coordinates[i]), reverse=True):
        if not alive[j]:
            continue
        x = coordinates[j]
        for k in range(j - 1, -1, -1):
            if x - coordinates[k] >= distance:
                break
            alive[k] = 0
        for k in range(j + 1, len(coordinates)):
            if coordinates[k] - x >= distance:
                break
            alive[k] = 0
    return peaks[np.frombuffer(alive, dtype=np.uint8).astype(bool)]


def extract_candidates(on, off, roi, reject_mask):
    """Return (row,num,den,tag,lo,hi,peak_x,strength) in FPGA record order."""
    if on.shape != off.shape or on.shape != (1920, 1080, 3):
        raise ValueError('expected matching rotated 1920x1080 RGB arrays')
    if on.dtype != np.uint8 or off.dtype != np.uint8:
        raise ValueError('expected uint8 images')
    left, top, right, bottom = map(int, roi)
    if not (4 <= left < right <= 1076 and 0 <= top < bottom <= 1920):
        raise ValueError('invalid ABI6 ROI')
    if reject_mask.shape != (bottom - top, 1080) or reject_mask.dtype != bool:
        raise ValueError('reject mask geometry/type mismatch')
    sig = _max_channel(cv2.subtract(on[top:bottom], off[top:bottom])).astype(np.uint16)
    mx = _max_channel(on[top:bottom])
    # Integer coefficients and a maximum sum of 4080 make this uint16 filter
    # exact; REFLECT_101 matches numpy.pad(mode='reflect') at both edges.
    sm = cv2.filter2D(sig, -1, np.asarray([[1, 4, 6, 4, 1]], np.float32),
                      borderType=cv2.BORDER_REFLECT_101)
    bases = (np.median(sm[:, left:right], axis=1) * 2).astype(np.int64)
    minimum_peaks = sm[:, left:right].min(axis=1).astype(np.int32) + 288
    possible_rows = np.flatnonzero(sm[:, left:right].max(axis=1) >= minimum_peaks)
    records = []
    for row in possible_rows.tolist():
        v = sm[row, left:right]
        # Prominence cannot exceed height minus the minimum of this ROI row.
        # Drop only peaks that provably cannot pass the later 288 test. They
        # are lower than every remaining peak, so descending-height suppression
        # would visit them last and cannot change any remaining peak's fate.
        # Keep equality: the canonical prominence comparison is >= 288.
        minimum_peak = minimum_peaks[row]
        peaks = find_peaks(v)[0]
        peaks = peaks[(v[peaks] >= minimum_peak) & ~reject_mask[row, peaks + left]]
        peaks = _suppress(peaks, v, 8)
        prom = peak_prominences(v, peaks)[0] if len(peaks) else np.array([])
        peaks = peaks[prom >= 288] + left
        local = []
        for r in evaluate(sig[row], sm[row], int(bases[row]), peaks, left, right - 1, SETTINGS):
            signal = int(sig[row, max(0, r['k'] - 3):r['k'] + 4].max())
            if r['reason'] or signal < 25:
                continue
            core(r, sm[row], int(bases[row]), SETTINGS)
            if r['reason']:
                continue
            xs = np.arange(r['core_lo'], r['core_hi'] + 1)
            weights = np.maximum(10 * (sm[row, xs].astype(np.int64) * 2 - bases[row]) - 7 * r['peak32'], 0)
            num, den = int((weights * xs).sum()), int(weights.sum())
            tag = 32768 + (256 if mx[row, r['lo']:r['hi'] + 1].max() >= 250 else 0) + signal
            local.append((top + row, num, den, tag, r['lo'], r['hi'], r['k'], r['peak32']))
        if len(local) > 16:
            raise ValueError('candidate capacity exceeded; reject whole frame')
        records.extend(local)
    return records
