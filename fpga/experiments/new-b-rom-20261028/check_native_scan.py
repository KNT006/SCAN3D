"""Read-only acceptance summary of a native-B full scan; no point modification."""
from pathlib import Path
import argparse, hashlib, json
import numpy as np
from scipy.stats import binned_statistic_2d

p = argparse.ArgumentParser()
p.add_argument('scan', type=Path)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
s = json.loads((a.scan / 'status.json').read_text())
with np.load(a.scan / 'combined.npz', allow_pickle=False) as f:
    xyz = f['xyz'].astype(float)
    labels = f['laser']
    positions = f['position']
assert xyz.shape == (len(labels), 3) and np.isfinite(xyz).all()
clouds = [xyz[labels == i] for i in (0, 1)]
assert all(len(c) > 0 for c in clouds)
low = max(float(np.percentile(c[:, 1], 2)) for c in clouds)
high = min(float(np.percentile(c[:, 1], 98)) for c in clouds)
y_edges = np.arange(np.floor(low / 2) * 2, np.ceil(high / 2) * 2 + 2, 2)
theta_edges = np.linspace(-np.pi, np.pi, 37)
medians, counts = [], []
for c in clouds:
    theta = np.arctan2(c[:, 2], c[:, 0])
    radius = np.hypot(c[:, 0], c[:, 2])
    medians.append(binned_statistic_2d(c[:, 1], theta, radius, statistic='median', bins=[y_edges, theta_edges])[0])
    counts.append(np.histogram2d(c[:, 1], theta, bins=[y_edges, theta_edges])[0])
valid = (counts[0] >= 3) & (counts[1] >= 3)
delta = (medians[1] - medians[0])[valid]
assert len(delta) > 0
report = dict(scan=str(a.scan), status=s.get('status'), scan_passed=s.get('passed'),
    completed_positions=s.get('completed_positions'), closure=s.get('closure'),
    retained_points={'A': len(clouds[0]), 'B': len(clouds[1])},
    combined_points=len(xyz), finite_points=True, position_count=len(np.unique(positions)),
    planes_sha256=hashlib.sha256((a.scan / 'bundle/planes.json').read_bytes()).hexdigest(),
    split_reconstruction_active=(a.scan / 'bundle/reconstruction_B.json').exists(),
    radial_comparison=dict(height_bin_mm=2, angle_bin_degrees=10, minimum_samples_per_laser=3,
        common_cells=int(valid.sum()), B_minus_A_p5_median_p95_mm=np.percentile(delta, [5,50,95]).tolist(),
        median_absolute_difference_mm=float(np.median(np.abs(delta)))),
    absolute_accuracy_validated=False,
    scope='A/B agreement in same-height/azimuth bins; occlusion and shape influence this metric, not caliper accuracy')
a.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
