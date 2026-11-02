"""Sample archived images, never the geometry or same-pose RGB used by reconstruction."""
import json
import math
import os
from pathlib import Path

ROLES = ('A', 'B', 'COLOR')
EXTENSIONS = ('png', 'ppm', 'jpg', 'jpeg')


def policy(step, intervals):
    step = float(step)
    if not math.isfinite(step) or step <= 0 or type(intervals) is not int or intervals < 1:
        raise ValueError('Invalid scan image schedule')
    stride = max(1, math.floor(6.0 / step + 0.5)) if step < 6 else 1
    return dict(version=1, target_degrees=6, step_degrees=step, stride=stride,
                nominal_degrees=round(stride * step, 8), intervals=intervals,
                roles=list(ROLES), keep_endpoints=True, geometry='all_positions')


def keep(index, rules):
    return index in (0, rules['intervals']) or index % rules['stride'] == 0


def frame_paths(folder):
    folder = Path(folder)
    return [folder / role / ('same-frame.' + ext) for role in ROLES for ext in EXTENSIONS
            if (folder / role / ('same-frame.' + ext)).is_file()]


def atomic_json(path, value):
    path = Path(path)
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def discard_frames(folder, rules):
    """Only run after reconstruction and same-pose colour sampling have succeeded."""
    folder = Path(folder)
    if folder.is_symlink():
        raise ValueError('Symlink position')
    folder = folder.resolve()
    index = int(folder.name.removeprefix('position-'))
    if keep(index, rules):
        return 0
    state = json.loads((folder / 'status.json').read_text())
    if state.get('status') != 'complete':
        raise ValueError('Cannot discard images before completed reconstruction')
    for role in ('A', 'B'):
        if not (folder / role / 'points.npz').is_file():
            raise ValueError('Missing reconstructed points')
    files = frame_paths(folder)
    records = []
    for f in files:
        if f.is_symlink() or f.parent.is_symlink() or folder not in f.resolve().parents:
            raise ValueError('Unsafe image path')
        records.append(dict(path=f.relative_to(folder).as_posix(), bytes=f.stat().st_size))
    # Persist intent first; an interrupted cleanup can safely be re-run.
    marker = folder / 'image-retention.json'
    if files:
        atomic_json(marker, dict(policy=rules, index=index, kept=False, removed=records, complete=False))
        for f in files:
            f.unlink()
        atomic_json(marker, dict(policy=rules, index=index, kept=False, removed=records, complete=True))
        storage = folder / 'lossless-storage.json'
        if storage.is_file():
            rows = json.loads(storage.read_text())
            for row in rows:
                if row.get('target', '').split('/')[0] in ROLES:
                    row['retained'] = False
                    row['retention_policy'] = 'six-degree-image-sampling-v1'
            atomic_json(storage, rows)
    return sum(r['bytes'] for r in records)


class SampledStorage:
    def __init__(self, rules):
        self.rules = rules

    def __call__(self, folder):
        from scan_storage import compress_position
        # Avoid PNG encoding/writing of discarded frames. Source PPMs are temporary
        # inputs required by the existing reconstruction and RGB sampling stages.
        discard_frames(folder, self.rules)
        return compress_position(folder)


def available_positions(root):
    def has(folder, role):
        return any((folder / role / ('same-frame.' + ext)).is_file() for ext in ('png', 'ppm'))
    return [int(p.name.split('-')[-1]) for p in sorted(Path(root).glob('position-*'),
            key=lambda p: int(p.name.split('-')[-1]))
            if (p / 'status.json').is_file() and all(has(p, role) for role in ('OFF', 'A', 'B'))]
