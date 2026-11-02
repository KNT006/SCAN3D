"""Archive actual board evidence and update the candidate's acceptance record."""
from pathlib import Path
import hashlib, json, tarfile, shutil

HERE = Path(__file__).resolve().parent
evidence = HERE / 'board-evidence'
evidence.mkdir(exist_ok=True)
with tarfile.open(HERE / 'final-evidence.tar.gz', 'r:gz') as archive:
    archive.extractall(evidence, filter='data')
job = evidence / 'new-B-ROM-20261028'
scan = json.loads((job / 'native-coarse-validation.json').read_text(encoding='utf-8'))
static = json.loads((job / 'native-gourd-validation/status.json').read_text(encoding='utf-8'))
flash = json.loads((HERE / 'program-flash-result.json').read_text(encoding='utf-8'))
replay = json.loads((job / 'native-archive-replay-test/result.json').read_text(encoding='utf-8'))
services = json.loads((job / 'final-services.json').read_text(encoding='utf-8'))
assert scan['scan_passed'] and scan['completed_positions'] == 61
assert scan['closure']['passed'] and scan['combined_points'] > 0
assert not scan['split_reconstruction_active']
assert static['passed'] and static['scan_ready'] and flash['passed']
assert all(static['lasers'][k]['comparison']['passed'] for k in ('A', 'B'))
assert replay['status'] == 'complete' and replay['baseline_comparison']['uv_equal']
assert not any(services['scanner'].get(k) for k in ('active_scans','active_jobs','active_calibrations'))
assert services['camera']['raw_age'] < 1 and services['camera']['raw_timeouts'] == 0
candidate_path = HERE / 'candidate.json'
candidate = json.loads(candidate_path.read_text())
candidate.update(hardware_validated=True, hardware_candidate_comparison_passed=True,
    object_scan_validated=True, flash_written=True, cold_boot_tested=False,
    board_scan='scan3d-20261028-214500-nativeb', absolute_accuracy_validated=False)
candidate_path.write_text(json.dumps(candidate, indent=2))
record = dict(passed=True, bit_sha256=candidate['sha256'],
    flash_verified=True, cold_boot_tested=False, object_scan=scan,
    gourd_static_exact_comparison={k:static['lasers'][k]['comparison'] for k in ('A','B')},
    native_replay_matches_archive=True, services_restored=True,
    evidence_sha256=hashlib.sha256((HERE/'final-evidence.tar.gz').read_bytes()).hexdigest(),
    absolute_accuracy_validated=False)
(HERE/'hardware-validation.json').write_text(json.dumps(record, indent=2))
host = json.loads((HERE/'host-patch.json').read_text());host['deployed']=True
(HERE/'host-patch.json').write_text(json.dumps(host,indent=2))
for name in ('candidate.json','hardware-validation.json','program-flash-result.json'):
    shutil.copyfile(HERE/name,Path(candidate['bit']).parent/name)
print(json.dumps(dict(passed=True, combined_points=scan['combined_points'], scan=candidate['board_scan'])))
