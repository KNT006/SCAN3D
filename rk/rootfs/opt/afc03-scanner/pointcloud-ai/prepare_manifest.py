"""Create an explicit review manifest from this project's saved COLOR frames."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--scan', type=Path, required=True)
parser.add_argument('--bundle', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--stride', type=int, default=2)
parser.add_argument('--rotation', type=int, choices=[0, 90, 180, 270], required=True)
args = parser.parse_args()
if args.stride < 1:
    parser.error('stride must be positive')
config = json.loads((args.bundle/'config.json').read_text())
schedule = config['angle_schedule']
pulses = config['pulses_per_revolution']
if pulses <= 0:
    raise ValueError('Invalid pulses per revolution')
views = []
seen_angles = set()
files = sorted(args.scan.glob('position-*/COLOR/same-frame.png'), key=lambda p: int(p.parts[-3].split('-')[1]))
for path in files[::args.stride]:
    index = int(path.parts[-3].split('-')[1])
    angle = schedule[index]*360/pulses
    key = round(angle % 360, 5)
    if key in seen_angles:
        continue
    seen_angles.add(key)
    views.append(dict(frame=index, path=str(path.resolve()), angle_degrees=angle, rotate_clockwise_degrees=args.rotation))
spec = dict(coordinate_frame='axis_frame_mm', angle_source='bundle commanded pulse schedule; no encoder verification',
            roi=config['scan_roi'], camera=json.loads((args.bundle/'camera.json').read_text()),
            axis=json.loads((args.bundle/'axis.json').read_text()), views=views)
with args.output.open('x', encoding='utf-8') as stream:
    json.dump(spec, stream, ensure_ascii=False, indent=2)
