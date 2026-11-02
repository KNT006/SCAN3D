from pathlib import Path
import json,paramiko,numpy as np,hashlib,posixpath
H=Path(__file__).resolve().parent;PC=H.parent/'pc-adaptive-stripes-20261009';source=PC/'input-latest-new-item';dest='/opt/afc03-scanner/candidates/rgb-adaptive-20261010'
s=paramiko.SSHClient();s.load_host_keys(str(Path.home()/'.ssh/afc03_motor_known_hosts'));s.connect('192.168.1.89',username='root',key_filename=str(Path.home()/'.ssh/afc03_motor_ed25519'),timeout=8);f=s.open_sftp()
def mkdir(p):
 try:f.stat(p)
 except FileNotFoundError:mkdir(posixpath.dirname(p));f.mkdir(p)
def put(p,q):mkdir(posixpath.dirname(q));f.put(str(p),q)
for p in (H/'host').glob('*.py'):put(p,dest+'/fpga/'+p.name)
for p in (source/'bundle').glob('*.json'):put(p,dest+'/replay/bundle/'+p.name)
for index in (0,34,59):
 folder=source/f'position-{index:03d}';put(folder/'COLOR/same-frame.png',dest+f'/replay/{index:03d}-COLOR.png')
 for laser in 'AB':
  case=f'{index:03d}-{laser}';put(H/'replay'/(case+'.bin'),dest+'/replay/'+case+'.bin');put(folder/laser/'frame.json',dest+'/replay/'+case+'.json')
  ref=json.loads((PC/'output/latest-new-item-rgb100-160'/case/'data.json').read_text(encoding='utf-8'))['modes']['early_adaptive']['points'];expected=H/'replay'/(case+'.expected.npz');np.savez(expected,uv=np.array([[r['x'],r['y']] for r in ref]).reshape(-1,2),xyz=np.array([r['xyz'] for r in ref]).reshape(-1,3));put(expected,dest+'/replay/'+expected.name)
print('Staged isolated candidate modules and 6 replay cases; active service untouched')
_,o,e=s.exec_command('cat /opt/afc03-scanner/fpga/bundle/spatial_filter.json; cat /opt/afc03-scanner/fpga/bundle/config.json',timeout=10);print(o.read().decode());print(e.read().decode());s.close()
