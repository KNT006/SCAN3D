"""Isolated ABI6 software candidate front end (no hardware imports or writes).

Batches pixel arithmetic with NumPy; peak evaluation still uses the audited
scalar helpers. This is an executable baseline, NOT an optimized RK upper bound.
Images are already clockwise rotated, shape (1920, 1080, 3); RGB/BGR ordering
is immaterial here because only per-channel differences/maxima are used.
LUT loading belongs to setup, outside steady-state frame timing.
"""
from pathlib import Path
import sys
import numpy as np
from scipy.signal import find_peaks, peak_prominences

FPGA = Path(__file__).resolve().parents[2] / 'rk/rootfs/opt/afc03-scanner/fpga'
if str(FPGA) not in sys.path:
    sys.path.insert(0, str(FPGA))
from spatial_reference import suppress, evaluate, core

SETTINGS = dict(prominence=18, distance=8, width_max=100,
                core_fraction=.7, core_radius=10)


def load_rom_mask(path, laser, roi):
    """Decode exact deployed-ROM-format reject intervals; never infer live ROM."""
    if laser not in ('A', 'B'):
        raise ValueError('laser must be A or B')
    words = [int(s.strip(), 16) for s in Path(path).read_text().splitlines() if s.strip()]
    if len(words) != 4096 or any(w < 0 or w >= 1 << 48 for w in words):
        raise ValueError('expected 4096 48-bit ROM words')
    left, top, right, bottom = map(int, roi)
    if not (0 <= top < bottom <= 1920 and 0 <= left < right <= 1080):
        raise ValueError('invalid ROI')
    x = np.arange(1080)
    rows = []
    for y in range(top, bottom):
        w = words[y + (2048 if laser == 'B' else 0)]
        rows.append(np.logical_or.reduce([
            (x >= ((w >> shift) & 4095)) & (x <= ((w >> (shift + 12)) & 4095))
            for shift in (0, 24)]))
    return np.asarray(rows, dtype=bool)


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
    sig = np.maximum(on[top:bottom].astype(np.int16) - off[top:bottom].astype(np.int16), 0).max(2).astype(np.uint16)
    mx = on[top:bottom].max(2)
    pad = np.pad(sig, ((0, 0), (2, 2)), mode='reflect')
    sm = sum(w * pad[:, i:i + 1080] for i, w in enumerate((1, 4, 6, 4, 1)))
    bases = (np.median(sm[:, left:right], axis=1) * 2).astype(np.int64)
    records = []
    for row in range(bottom - top):
        v = sm[row, left:right]
        peaks = find_peaks(v)[0]
        peaks = peaks[~reject_mask[row, peaks + left]]
        peaks = suppress(peaks, v, 8)
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


def candidate_uv(records):
    return np.asarray([[r[1] / r[2], r[0]] for r in records], dtype=float).reshape(-1, 2)


def compare_uv(records, expected, tolerance=1e-8):
    """Coordinate-only archive check; cannot certify metadata or downstream parity."""
    actual = candidate_uv(records)
    expected = np.asarray(expected, dtype=float).reshape(-1, 2)
    if not np.isfinite(expected).all():
        raise ValueError('nonfinite expected coordinates')
    def sort(a):
        return a[np.lexsort((a[:, 0], a[:, 1]))] if len(a) else a
    a, e = sort(actual), sort(expected)
    same_count = len(a) == len(e)
    error = float(np.max(np.abs(a - e))) if same_count and len(a) else (0.0 if same_count else None)
    return dict(scope='candidate_uv_only', actual_count=len(a), expected_count=len(e),
                passed=bool(same_count and error <= tolerance), max_abs_error=error,
                tolerance=tolerance, metadata_verified=False)
