"""Activate only new-B planes/binding; preserve all production scan settings."""
from pathlib import Path
import hashlib, json, shutil

JOB = Path('/userdata/afc03-scanner/jobs/new-B-ROM-20261028')
ROOT = Path('/opt/afc03-scanner/fpga')
BUNDLE = ROOT / 'new-strategy-bundle'
OLD = '4c1c3e00a5bbb2ae41355cfeefa6100081813846b8bca1e2b3da9be7ec5ab0a9'
NEW = '4219e460decd036b1d0afd9049601c4bb8e18f151a776e9e32b9afb9aa319d61'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
source = ROOT / 'rgb_adaptive_strategy.py'
original = source.read_bytes()
assert original.count(OLD.encode()) == 1
patched = original.replace(OLD.encode(), NEW.encode())
assert patched == (JOB / 'rk-rgb-adaptive-native.py').read_bytes()
assert sha(BUNDLE / 'planes.json') == OLD
assert sha(JOB / 'planes.json') == NEW
before = json.loads((BUNDLE / 'planes.json').read_text())
after = json.loads((JOB / 'planes.json').read_text())
assert before['planes']['laser_A'] == after['planes']['laser_A']
config = json.loads((BUNDLE / 'config.json').read_text())
assert config['sha256']['planes.json'] == OLD
backup = JOB / 'activation-backup'
backup.mkdir(exist_ok=False)
targets = [source, BUNDLE / 'planes.json', BUNDLE / 'config.json', BUNDLE / 'reconstruction_B.json']
for p in targets:
    if p.exists():
        shutil.copy2(p, backup / p.name)
def replace(p, data):
    tmp = p.with_name(p.name + '.new-B-tmp')
    tmp.write_bytes(data)
    shutil.copystat(p, tmp)
    tmp.replace(p)
replace(source, patched)
replace(BUNDLE / 'planes.json', (JOB / 'planes.json').read_bytes())
config['sha256']['planes.json'] = NEW
replace(BUNDLE / 'config.json', json.dumps(config, indent=2).encode())
profile = BUNDLE / 'reconstruction_B.json'
if profile.exists():
    profile.rename(BUNDLE / 'reconstruction_B.software-backup-20261028.json')
record = dict(planes_sha256=sha(BUNDLE / 'planes.json'), host_sha256=sha(source),
              native_B=True, split_reconstruction_active=profile.exists(),
              changed=['planes.json', 'config.json sha256.planes.json', 'rgb_adaptive_strategy.py planes binding'],
              backup=str(backup), absolute_accuracy_validated=False)
(JOB / 'activation.json').write_text(json.dumps(record, indent=2))
print(json.dumps(record))
