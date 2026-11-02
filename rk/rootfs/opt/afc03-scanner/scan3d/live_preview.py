"""Read-only, bounded preview. Cursor is discovery, NOT acknowledgement.

Clients retain every gap until its chunk is received (including empty chunks).
No scan/export file is written; direct numbered paths avoid directory rescans.
"""
import json
import logging
import time
import zipfile
from functools import lru_cache
import numpy as np

# Inherit the service's configured INFO handler rather than the silent root logger.
LOG = logging.getLogger('uvicorn.error.scan3d.preview')
BUDGET = 160000
MAX_POSITIONS = 3201


@lru_cache(maxsize=8)
def legacy_last(path, time_bucket):
    # Only archives lacking producer counters need directory discovery. TTL also
    # notices a late-published position; no persisted index can go stale on reboot.
    return max((int(p.name[9:]) for p in path.glob('position-*')
                if p.name[9:].isdigit()), default=-1)


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def preview_page(path, after=-1, retry=''):
    started = time.monotonic()
    if not -1 <= after < MAX_POSITIONS:
        raise ValueError('invalid preview cursor')
    retries = list(dict.fromkeys(int(v) for v in retry.split(',') if v))
    if len(retries) > 8 or any(v < 0 or v >= MAX_POSITIONS for v in retries):
        raise ValueError('invalid preview retry positions')
    st = read_json(path/'status.json')
    planned = st.get('planned_intervals')
    slots = min(MAX_POSITIONS, max(1, int(planned) if planned else MAX_POSITIONS))
    quota = min(2048, BUDGET // slots)
    # completed_positions is the producer's published prefix. Include the current
    # position for older/preflight tasks; failed reads remain explicit gaps.
    last = min(slots-1, max(int(st.get('completed_positions', 0))-1,
                           int(st.get('last_index', -1))))
    if 'completed_positions' not in st and 'last_index' not in st:
        last = min(slots-1, legacy_last(path, int(time.monotonic()/2)))
    if last < 0 and (path/'position-000').is_dir():
        last = 0
    indices = list(dict.fromkeys(retries + list(range(after+1, min(last+1, after+9)))))
    chunks, gaps, cursor, count = [], [], after, 0
    for index in indices:
        if count + quota > 4096 or len(chunks)+len(gaps) >= 16:
            break
        folder = path/f'position-{index:03d}'
        report = read_json(folder/'status.json')
        reason = ''
        if report.get('status') != 'complete':
            reason = 'not_complete'
        else:
            try:
                xyz, rgb = [], []
                for label in ('A', 'B'):
                    with np.load(folder/label/'points.npz', allow_pickle=False) as d:
                        x, c = d['axis_frame_mm'], d['rgb']
                        if x.ndim != 2 or x.shape[1] != 3 or c.shape != x.shape:
                            raise ValueError('coordinate/color shape mismatch')
                        if not np.isfinite(x).all() or not np.isfinite(c).all():
                            raise ValueError('nonfinite coordinate/color')
                        xyz.append(x); rgb.append(c)
                x, c = np.concatenate(xyz), np.concatenate(rgb)
                # Equal angular allocation; uniformly sample each position.
                take = np.linspace(0, len(x)-1, min(len(x), quota), dtype=int)
                chunk = dict(index=index, xyz=np.round(x[take], 3).tolist(),
                             rgb=np.clip(c[take], 0, 255).astype(np.uint8).tolist(),
                             source_count=len(x))
                chunks.append(chunk); count += len(take)
            except FileNotFoundError:
                reason = 'file_not_published'
            except (OSError, ValueError, KeyError, EOFError, zipfile.BadZipFile) as e:
                reason = 'read_failed: '+str(e)[:160]
        if reason:
            gaps.append(dict(index=index, reason=reason))
        if index > cursor:
            cursor = index
    elapsed = round((time.monotonic()-started)*1000, 2)
    if chunks or gaps or elapsed > 200:
        LOG.info('preview run=%s after=%s cursor=%s points=%s ms=%s gaps=%s',
                 path.name, after, cursor, count, elapsed, gaps)
    return dict(id=path.name, protocol=2, chunks=chunks, gaps=gaps, cursor=cursor,
                available_through=last, quota=quota, budget=BUDGET,
                points=count, elapsed_ms=elapsed, units='mm',
                provisional=not bool(st.get('passed')))
