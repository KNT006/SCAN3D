from pathlib import Path
import sys,json,hashlib,paramiko
H=Path(__file__).resolve().parent;C='/opt/afc03-scanner/candidates/rgb-adaptive-20261010'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest={p.name:sha(p) for p in (H/'host').glob('*.py')}
(H/'host-candidate-manifest.json').write_text(json.dumps(manifest,indent=2))
script=(H.parent/'fpga-capture-pipeline-20261004/static_acceptance.py').read_text()
script=script.replace("str(H/'host')","str(H/'fpga')").replace('capture-pipeline-20261004','rgb-adaptive-20261010')
script=script.replace("Path('/opt/afc03-scanner/fpga/new-strategy-bundle')","H/'acceptance-bundle'")
(H/'static_acceptance.py').write_text(script)
s=paramiko.SSHClient();s.load_host_keys(str(Path.home()/'.ssh/afc03_motor_known_hosts'));s.connect('192.168.1.89',username='root',key_filename=str(Path.home()/'.ssh/afc03_motor_ed25519'),timeout=8)
f=s.open_sftp()
for folder in ('scan3d','acceptance-bundle'):
 try:f.mkdir(C+'/'+folder)
 except OSError:pass
for p in (H/'host').glob('*.py'):f.put(str(p),C+'/fpga/'+p.name)
for p in [H/'static_acceptance.py',H/'host-candidate-manifest.json']:f.put(str(p),C+'/'+p.name)
f.put(str(H/'scan3d/runner.py'),C+'/scan3d/runner.py')
f.get(C+'/rk-replay-validation.json',str(H/'rk-replay-validation.json'))
# Snapshot current production bundle, including the expanded ROI; stage only.
code=r'''
from pathlib import Path
import json,shutil,hashlib
C=Path('/opt/afc03-scanner/candidates/rgb-adaptive-20261010')
P=Path('/opt/afc03-scanner/fpga/new-strategy-bundle');B=C/'acceptance-bundle'
for p in P.glob('*.json'):shutil.copy2(p,B/p.name)
sp=json.loads(Path('/userdata/afc03-scanner/jobs/scan3d-work/spatial-profile.json').read_text())
assert sp['enabled'] and sp['radius_mm']==70 and sp.get('margin_mm',0)==0
sp['axis_sha256']=hashlib.sha256((B/'axis.json').read_bytes()).hexdigest()
(B/'spatial_filter.json').write_text(json.dumps(sp,indent=2))
print(json.dumps(dict(roi=json.loads((B/'config.json').read_text())['scan_roi'],spatial=sp)))
'''
_,o,e=s.exec_command('/usr/bin/python3 -',timeout=30);o.channel.sendall(code.encode());o.channel.shutdown_write();print(o.read().decode(),e.read().decode());assert o.channel.recv_exit_status()==0
s.close()
