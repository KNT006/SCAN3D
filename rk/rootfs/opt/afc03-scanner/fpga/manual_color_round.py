"""Dedicated colour pass using the frozen pulse runner; no legacy UART moves."""
import argparse
import fcntl
import json
from pathlib import Path
import signal
import sys
import urllib.request
import cv2
import numpy as np


def appearance_check(a, b, roi, limit=1.5):
    gray = [cv2.cvtColor(im, cv2.COLOR_BGR2GRAY) for im in (a, b)]
    mask = np.zeros(gray[0].shape, np.uint8)
    x0, y0, x1, y1 = roi
    mask[y0:y1, x0:x1] = 255
    p = cv2.goodFeaturesToTrack(gray[0], 250, .02, 8, mask=mask)
    if p is None:
        return dict(passed=False, reason='No texture features')
    q, good, err = cv2.calcOpticalFlowPyrLK(gray[0], gray[1], p, None, winSize=(21, 21), maxLevel=3)
    back, good_back, _ = cv2.calcOpticalFlowPyrLK(gray[1], gray[0], q, None, winSize=(21, 21), maxLevel=3)
    keep = good.ravel().astype(bool) & good_back.ravel().astype(bool)
    keep &= np.linalg.norm((back-p).reshape(-1, 2), axis=1) < .5
    keep &= err.ravel() < 20
    delta = np.linalg.norm((q-p).reshape(-1, 2), axis=1)[keep]
    p95 = float(np.percentile(delta, 95)) if len(delta) else None
    return dict(tracked=int(len(delta)), features=int(len(p)), p95_px=p95,
                median_px=float(np.median(delta)) if len(delta) else None,
                passed=bool(len(delta) >= 30 and len(delta) >= .6*len(p) and p95 < limit), limit_px=limit)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--bundle', type=Path, required=True)
    ap.add_argument('--session', type=Path, required=True)
    ap.add_argument('--phase', choices=['prepare', 'scan'], required=True)
    args = ap.parse_args()
    sys.path.insert(0, str(args.bundle))
    from manual_round import Runner, read, write, PLAN as GEOMETRY_PLAN
    from scan_plan import storage_precheck, color_plan
    PLAN = color_plan(read(args.bundle / 'config.json'))
    target = PLAN.target
    lock = open('/run/afc03-manual-dual.lock', 'w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    with urllib.request.urlopen('http://127.0.0.1:8081/api/status', timeout=5) as response:
        s = json.load(response)
    if s.get('active_scans') or s.get('active_jobs') or s.get('active_calibrations'):
        raise RuntimeError('Other scanner work active')
    for label in ['A', 'B']:
        geometry = read(args.session / label / 'state.json')
        if (geometry['status'] != 'completed_commanded_round'
                or geometry.get('plan') != GEOMETRY_PLAN.describe()
                or geometry['last_index'] != GEOMETRY_PLAN.intervals):
            raise RuntimeError('Geometry not complete')
    folder = args.session / 'color-01'
    folder.mkdir(exist_ok=True)
    roi = read(args.bundle / 'config.json')['scan_roi']
    storage_precheck(args.session, PLAN, 'color')
    prepared = read(args.session/'prepared.json')
    import hashlib
    if prepared.get('config_sha256') != hashlib.sha256((args.bundle/'config.json').read_bytes()).hexdigest():
        raise RuntimeError('Session/profile mismatch')
    runner = Runner(args.session)
    runner.cfg['settle_seconds'] = runner.cfg.get('color_settle_seconds', 1.2)
    def stop(signum, frame):
        raise RuntimeError('Operator termination; no motion replay')
    signal.signal(signal.SIGTERM, stop)
    state = None
    try:
        runner.check()
        runner.last_raw = (read(args.session / 'prepared.json')['camera_stream'], -1)
        if args.phase == 'prepare':
            runner.settings(0, 0)
            runner.pair(folder, 'lasers-off')
            runner.settings(50, 8)
            ims, rec = runner.pair(folder, 'appearance')
            original = cv2.rotate(cv2.imread(str(args.session / 'appearance-0.png')), cv2.ROTATE_90_CLOCKWISE)
            pair_check = appearance_check(*ims, roi)
            origin_check = appearance_check(original, ims[0], roi, limit=3.0)
            runner.flush_pending()
            write(folder / 'preflight.json', dict(pair=pair_check, origin=origin_check,
                  verified=False, gain=50, led=8, lasers='both_off_operator_confirmed', motor_moved=False))
            print(json.dumps(read(folder / 'preflight.json')), flush=True)
            return
        pre = read(folder / 'preflight.json')
        if not pre['verified'] or not pre['origin']['passed'] or not pre['pair']['passed']:
            raise RuntimeError('Review and accept preflight before motion')
        statefile = folder / 'state.json'
        if statefile.exists():
            raise RuntimeError('Existing color round; never replay automatically')
        state = dict(plan=PLAN.describe(), status='running', last_index=-1, angle_source='commanded_pulses_no_encoder')
        write(statefile, state)
        runner.settings(50, 8)
        first = None
        for i in range(PLAN.intervals+1):
            if i:
                runner.move(target(i)-target(i-1), folder / f'move{i:03d}.json')
            ims, rec = runner.pair(folder, f'position{i:03d}', color=True)
            check = appearance_check(*ims, roi)
            runner.flush_pending()
            write(folder / f'position{i:03d}-quality.json', check)
            if not check['passed']:
                raise RuntimeError('Color pair unstable: '+str(check))
            if i == 0:
                pre_im = cv2.rotate(cv2.imread(str(folder / 'appearance-0.png')), cv2.ROTATE_90_CLOCKWISE)
                q = appearance_check(pre_im, ims[0], roi)
                write(folder / 'start-check.json', q)
                if not q['passed']:
                    raise RuntimeError('Scene changed since preflight')
                first = ims[0]
            state['last_index'] = i
            write(statefile, state)
            print(json.dumps(dict(phase='color', index=i, degrees=PLAN.angle(i))), flush=True)
        q = appearance_check(first, ims[0], roi, limit=3.0)
        write(folder / 'return-closure.json', q)
        if not q['passed']:
            raise RuntimeError('Color round return closure failed; do not apply texture')
        state['status'] = 'completed_commanded_round'
        write(statefile, state)
    except BaseException as exc:
        if state is not None:
            state.update(status='failed_no_auto_resume', error=str(exc))
            write(folder / 'state.json', state)
        raise
    finally:
        runner.close()


if __name__ == '__main__':
    main()
