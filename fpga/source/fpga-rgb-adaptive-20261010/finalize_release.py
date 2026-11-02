"""Record deployment only after matching programming and live-board evidence."""
from pathlib import Path
import json, shutil, time, hashlib

H = Path(__file__).resolve().parent
def read(name):
    return json.loads((H / name).read_text())

q = read('qualified.json')
flash = read('program-flash-result.json')
live = read('postflash-verification.json')
host = read('activated-host.json')
hardware = read('hardware-validation.json')
production = read('static-production.json')
assert all(v['passed'] for v in (flash, live, host, hardware))
assert production['passed'] and production['mode']=='production' and production['count']>=1
assert production['before']['session']==production['after']['session'] and production['before']['emitted']==production['after']['emitted']
for position in production['results']:
    r=position['report']
    assert r['passed'] and r['scan_ready']
    for laser in 'AB':
        a=r['lasers'][laser]
        assert a['strategy']['version']=='fpga-spatial25-rk-localrgb100-160-protected-v1'
        assert a['comparison']['passed'] and a['comparison']['mismatch_rows']==0 and a['comparison']['exact_rational_and_metadata']
assert flash['sha256'] == live['fpga_sha256'] == host['fpga_sha256'] == hardware['sha256'] == q['sha256']
assert flash['flash_written'] and q['hardware_validated']
assert hashlib.sha256(Path(q['bit']).read_bytes()).hexdigest() == q['sha256']
q['flash_written'] = True
q['cold_boot_tested'] = False
(H / 'qualified.json').write_text(json.dumps(q, indent=2))
report = dict(status='deployed_and_flash_verified', recorded_at=time.strftime('%Y-%m-%d %H:%M:%S'),
              qualified=q, production_activated=True, motor_moved=False, cold_boot_tested=False,
              pc_replay_cases=122, rk_replay_cases=6, static_positions=4, production_static_positions=production['count'],
              strategy='fpga-spatial25-rk-localrgb100-160-protected-v1',
              setup_wns_ns=read('timing-qualification.json')['setup_wns_ns'],
              hold_wns_ns=read('timing-qualification.json')['hold_wns_ns'],
              rollback_host=host['backup'],
              candidate_root='/opt/afc03-scanner/candidates/rgb-adaptive-20261010',
              ui_offline_replay_migrated=False)
(H / 'deployment-status.json').write_text(json.dumps(report, indent=2))
archive=Path(q['bit']).parent
for name in ('qualified.json','program-result.json','program-flash-result.json','program-flash.log',
             'hardware-validation.json','activated-host.json','postflash-verification.json','static-production.json','deployment-status.json'):
    shutil.copy2(H/name, archive/name)
print(json.dumps(report))
