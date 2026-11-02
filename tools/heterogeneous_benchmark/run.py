"""Read-only ABI6 candidate benchmark. No device imports, control calls, or writes to archives."""
import argparse
import hashlib
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from candidates import extract_candidates, load_rom_mask, compare_uv


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def peak_rss():
    if sys.platform != 'win32':
        import resource
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(value if sys.platform == 'darwin' else value * 1024)
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
            'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
            'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]
    c = Counters(); c.cb = ctypes.sizeof(c)
    ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    ok = ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(),
                                                ctypes.byref(c), c.cb)
    return int(c.PeakWorkingSetSize) if ok else None


def check_idle(url):
    import urllib.request
    with urllib.request.urlopen(url, timeout=4) as response:
        state = json.load(response)
    helper = state.get('helper', {})
    if state.get('active') or state.get('mesh_processing') or helper.get('worker_running') or helper.get('manual_motion'):
        raise RuntimeError('Device busy: benchmark aborted without stopping the active task')


def environment():
    info = {}
    for name in ('meminfo', 'swaps', 'loadavg'):
        path = Path('/proc')/name
        if path.exists(): info[name] = path.read_text()
    info['temperatures_millicelsius'] = {str(p):p.read_text().strip() for p in Path('/sys/class/thermal').glob('thermal_zone*/temp')}
    info['cpu_frequency_khz'] = {str(p):p.read_text().strip() for p in Path('/sys/devices/system/cpu').glob('cpufreq/policy*/scaling_cur_freq')}
    return info


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--samples', type=Path, required=True)
    p.add_argument('--rom', type=Path, action='append', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--idle-url', help='Required when running on ARM; checked before every extraction')
    a = p.parse_args()
    if a.output.exists(): p.error('Output exists; choose a new result file')
    if not 1 <= a.repeats <= 30: p.error('repeats must be 1..30')
    machine = platform.machine().lower()
    if ('arm' in machine or 'aarch' in machine) and not a.idle_url:
        p.error('ARM board runs require --idle-url')
    cv2.setNumThreads(1)
    hardware_lock = None
    if a.idle_url:
        import fcntl
        check_idle(a.idle_url)
        hardware_lock = open('/run/lock/afc03-fpga-scan.lock', 'a')
        fcntl.flock(hardware_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        check_idle(a.idle_url)
    def idle():
        if a.idle_url: check_idle(a.idle_url)
    result = dict(schema=1, host=platform.platform(), machine=machine,
        python=platform.python_version(), numpy=np.__version__, opencv=cv2.__version__,
        scope='ABI6 candidate extraction only; NOT whole RK scan or FPGA speedup',
        archive_validation='UV-only diagnostic; saved hardware frame metadata is not present in these samples',
        rss_scope='cumulative process high-water mark, including imports and setup',
        environment_start=environment(), roms=[dict(path=str(r), sha256=digest(r)) for r in a.rom], samples=[])
    a.output.parent.mkdir(parents=True, exist_ok=True)
    for data in sorted(a.samples.glob('*/data.json')):
        idle()
        meta = json.loads(data.read_text(encoding='utf-8'))
        laser = meta['request']['laser']; roi = meta['roi']
        paths = [data.parent/'OFF.png', data.parent/(laser+'.png')]
        entry = dict(sample=data.parent.name, roi=roi, laser=laser,
            inputs=[dict(path=str(x), sha256=digest(x)) for x in [data, *paths]], comparisons=[])
        t = time.perf_counter()
        images = [cv2.imread(str(x)) for x in paths]
        if any(x is None or x.shape != (1080,1920,3) for x in images):
            raise ValueError('Missing or non-native image: '+str(data))
        off, on = [cv2.rotate(x, cv2.ROTATE_90_CLOCKWISE) for x in images]
        entry['read_decode_rotate_seconds'] = time.perf_counter()-t
        expected = meta['steps'][0]['uv']
        for rom in a.rom:
            idle(); t = time.perf_counter()
            mask = load_rom_mask(rom, laser, roi)
            setup = time.perf_counter()-t
            records = extract_candidates(on, off, roi, mask)
            parity = compare_uv(records, expected)
            if 'expected_records' in meta:
                parity['metadata_verified'] = records == [tuple(x) for x in meta['expected_records']]
                parity['passed'] = parity['passed'] and parity['metadata_verified']
                parity['scope'] = 'candidate_rational_and_metadata'
            trial = dict(rom_sha256=digest(rom), setup_seconds=setup, parity=parity,
                         candidates=len(records), timings=[])
            for _ in range(a.repeats):
                idle(); wall=time.perf_counter(); cpu=time.process_time()
                repeated=extract_candidates(on,off,roi,mask)
                cpu=time.process_time()-cpu; wall=time.perf_counter()-wall
                if repeated != records: raise RuntimeError('Non-deterministic output')
                trial['timings'].append(dict(wall_seconds=wall,cpu_seconds=cpu))
            walls=[x['wall_seconds'] for x in trial['timings']]
            trial.update(median_seconds=statistics.median(walls),p95_seconds=float(np.percentile(walls,95)),
                         process_peak_rss_bytes=peak_rss())
            entry['comparisons'].append(trial)
        result['samples'].append(entry)
        result['environment_end'] = environment()
        a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(entry['sample'], 'completed', flush=True)
    print('Saved',a.output)


if __name__ == '__main__': main()
