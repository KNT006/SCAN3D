"""Read-only retrieval of the existing cat scan; no hardware or service commands."""
from pathlib import Path
import paramiko,numpy as np,json
out=Path(__file__).parent/'assets/cat-photo-source'
remote='/userdata/afc03-scanner/jobs/scan3d-20260427-214255-3f97df'
s=paramiko.SSHClient();s.load_host_keys(str(Path.home()/'.ssh/afc03_motor_known_hosts'))
s.connect('192.168.1.89',username='root',key_filename=str(Path.home()/'.ssh/afc03_motor_ed25519'),timeout=8)
try:
 f=s.open_sftp()
 names=['bundle/camera.json']
 for i in np.unique(np.linspace(0,179,49,dtype=int)):
  names += [f'position-{i:03d}/{p}' for p in ['COLOR/same-frame.png','A/points.npz','B/points.npz']]
 for i,name in enumerate(names):
  target=out/name;target.parent.mkdir(parents=True,exist_ok=True)
  if not target.exists():f.get(remote+'/'+name,str(target))
  if i%20==0:print(f'cat source {i+1}/{len(names)}',flush=True)
finally:s.close()
