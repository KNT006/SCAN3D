"""Pre-ROI reference retained only for diagnostic parity benchmarks."""
import cv2
import numpy as np
def stripe(image, background, roi):
    x0, y0, x1, y1 = roi
    signal = cv2.subtract(image, background).max(2)
    points, widths = [], []
    rejected = dict(weak=0, width=0, saturated=0)
    for y in range(y0, y1):
        row = signal[y, x0:x1].astype(float)
        k = int(row.argmax()); peak = row[k]
        if peak < 18:
            rejected['weak'] += 1; continue
        lo = hi = k; threshold = max(10, peak*.45)
        while lo > 0 and row[lo-1] >= threshold: lo -= 1
        while hi+1 < len(row) and row[hi+1] >= threshold: hi += 1
        if not 2 <= hi-lo+1 <= 35:
            rejected['width'] += 1; continue
        if image[y, x0+lo:x0+hi+1].max() >= 250:
            rejected['saturated'] += 1; continue
        weights = row[lo:hi+1]
        points.append([x0+np.dot(np.arange(lo, hi+1), weights)/weights.sum(), y])
        widths.append(hi-lo+1)
    return np.array(points).reshape(-1, 2), np.array(widths), rejected

