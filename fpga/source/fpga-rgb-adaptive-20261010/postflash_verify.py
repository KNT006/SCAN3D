"""Read-only production verification after Flash programming and PCIe restore."""
from pathlib import Path
from contextlib import ExitStack
import hashlib
import json
import subprocess
import sys
import time
import urllib.request

H = Path(__file__).resolve().parent
P = Path('/opt/afc03-scanner/fpga')
sys.path[:0] = [str(P), '/opt/afc03-scanner/vendor']
from rk_laser_ready import load_hardware_helpers, diagnostic_locks, inspect_or_release

manifest = json.loads((H/'deployment.json').read_text())
assert manifest['passed']
for name, digest in manifest['changed_sha256'].items():
    assert hashlib.sha256((P.parent/name).read_bytes()).hexdigest() == digest, name

def idle():
    from rk_rgb_roi_diag import scanner_idle
    return scanner_idle('http://127.0.0.1:8081')

DDR, Probe, MMIO, _ = load_hardware_helpers()
with ExitStack() as stack:
    diagnostic_locks(stack)
    idle()
    probe = Probe(); stack.callback(probe.close)
    ddr = DDR(probe.node.name); stack.callback(ddr.close)
    mmio = MMIO(probe)
    abi = mmio.read(0x2408)
    assert abi == 0x60000, hex(abi)
    assert mmio.read(0x2434)==0x9c744450 and mmio.read(0x2438)==0x0046000b
    assert probe.read(8) == 0x20000
    ready = inspect_or_release(ddr, probe, mmio, release=False, scanner_check=idle)
    state = ready['legacy_before']
    assert state['bridge_ready'] and state['init_advisory']['control_ready']
    assert not any(state[k] for k in ('reset_held', 'timeout', 'rejected'))

camera = json.load(urllib.request.urlopen('http://127.0.0.1:8080/status', timeout=5))
assert camera['frames'] > 5 and camera['age'] < 1 and camera['raw_age'] < 1
assert all(camera[k] == 0 for k in ('raw_bad_sizes', 'raw_timeouts', 'raw_pts_nonmonotonic'))
services = {}
for name in ('afc03-pcie', 'afc03-fpga-ready', 'afc03-camera', 'afc03-scanner'):
    active = subprocess.run(['systemctl', 'is-active', name], capture_output=True, text=True)
    enabled = subprocess.run(['systemctl', 'is-enabled', name], capture_output=True, text=True)
    assert active.returncode == enabled.returncode == 0, (name, active.stdout, enabled.stdout)
    services[name] = dict(active=active.stdout.strip(), enabled=enabled.stdout.strip())
report = dict(passed=True, fpga_sha256=manifest['fpga_sha256'], job_abi=hex(abi),
              probe_abi='0x00020000', camera=camera, services=services,
              ready=ready, cold_boot_tested=False, recorded_unix=time.time())
(H/'postflash-verification.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report))
