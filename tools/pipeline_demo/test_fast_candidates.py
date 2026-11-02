"""Exact record parity and a reproducible CPU benchmark (no board controls)."""
from pathlib import Path
import sys
import time
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'heterogeneous_benchmark'))
from candidates import extract_candidates as reference, suppress
from fast_candidates import extract_candidates as accelerated, _suppress


def scene(seed=10):
    rng = np.random.default_rng(seed)
    off = rng.integers(15, 90, (1920, 1080, 3), dtype=np.uint8)
    on = np.clip(off.astype(np.int16) + rng.integers(-9, 10, off.shape, dtype=np.int16), 0, 255).astype(np.uint8)
    x = np.arange(1080)
    for y in range(1000, 1660):
        curve = 300 + 75 * np.sin(y / 110)
        signal = 140 * np.exp(-((x - curve) / 4.5) ** 2)
        signal += 80 * np.exp(-((x - 650 - 25 * np.cos(y / 60)) / 7) ** 2)
        on[y, :, 0] = np.clip(on[y, :, 0].astype(float) + signal, 0, 255).astype(np.uint8)
    return on, off


class FastCandidatesTests(unittest.TestCase):
    def test_prominence_pruning_matches_unpruned_with_noise_and_plateaus(self):
        # In particular exercise low peaks beside a valid peak, equality at
        # the prominence boundary, ROI boundaries and masked stronger peaks.
        rng = np.random.default_rng(81)
        off = np.zeros((1920, 1080, 3), np.uint8)
        on = off.copy()
        roi = (4, 80, 1076, 160)
        on[80:160] = rng.integers(0, 21, (80, 1080, 3), dtype=np.uint8)
        x = np.arange(1080)
        for y in range(80, 160):
            for center, height, width in ((7, 25, 2), (300, 90, 4), (306, 55, 3), (700, 150, 5)):
                signal = height*np.exp(-((x-center)/width)**2)
                on[y, :, 0] = np.clip(on[y, :, 0].astype(float)+signal, 0, 255).astype(np.uint8)
        on[80, :, :] = 0
        on[81, :, :] = 18
        on[82, 100:150, :] = 18
        on[83, 100:150, :] = 19
        mask = rng.random((80, 1080)) < .05
        self.assertEqual(accelerated(on, off, roi, mask), reference(on, off, roi, mask))

    def test_suppression_random_ties_and_edges(self):
        rng = np.random.default_rng(33)
        for _ in range(100):
            values = rng.integers(0, 8, 740, dtype=np.uint16)
            peaks = np.sort(rng.choice(740, size=150, replace=False))
            np.testing.assert_array_equal(_suppress(peaks, values, 8), suppress(peaks, values, 8))
        np.testing.assert_array_equal(_suppress(np.array([], dtype=int), np.zeros(10), 8), [])

    def test_full_frame_A_B_records_match(self):
        on, off = scene()
        roi = (140, 1000, 880, 1660)
        for laser in ('A', 'B'):
            mask = np.zeros((660, 1080), dtype=bool)
            if laser == 'B':
                mask[:, 280:370] = True
                mask[100:250, 590:680] = True
            self.assertEqual(accelerated(on, off, roi, mask), reference(on, off, roi, mask))

    def test_empty_flat_wide_plateau_and_edge(self):
        off = np.zeros((1920, 1080, 3), np.uint8)
        on = off.copy()
        roi = (4, 10, 1076, 30)
        for y in range(10, 30):
            on[y, 4:10, 0] = 255
            on[y, 120:123, 1] = 25
            on[y, 160:180, 2] = 150
            on[y, 300:500, 0] = 100
            on[y, 700:705, :] = 255
        mask = np.zeros((20, 1080), bool)
        for current in (off, on):
            self.assertEqual(accelerated(current, off, roi, mask), reference(current, off, roi, mask))


def benchmark():
    on, off = scene()
    mask = np.zeros((660, 1080), dtype=bool)
    roi = (140, 1000, 880, 1660)
    result = {}
    expected = reference(on, off, roi, mask)
    for name, fn in [('reference', reference), ('accelerated', accelerated)]:
        fn(on, off, roi, mask)
        samples = []
        for _ in range(5):
            start = time.perf_counter()
            actual = fn(on, off, roi, mask)
            samples.append(round((time.perf_counter() - start) * 1000, 3))
            assert actual == expected
        result[name] = {'milliseconds': samples, 'median_ms': round(float(np.median(samples)), 3)}
    result['records'] = len(expected)
    result['speedup'] = round(result['reference']['median_ms']/result['accelerated']['median_ms'], 3)
    print(result)


if __name__ == '__main__':
    if '--benchmark' in sys.argv:
        benchmark()
    else:
        unittest.main()
