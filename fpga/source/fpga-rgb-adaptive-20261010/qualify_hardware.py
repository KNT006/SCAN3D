from pathlib import Path
import json,hashlib,paramiko
H=Path(__file__).resolve().parent;C='/opt/afc03-scanner/candidates/rgb-adaptive-20261010'
q=json.loads((H/'qualified.json').read_text());p=json.loads((H/'program-result.json').read_text());assert p['passed'] and p['sha256']==q['sha256'] and p['mode']=='sram'
m=json.loads((H/'host-candidate-manifest.json').read_text());assert all(hashlib.sha256((H/'host'/n).read_bytes()).hexdigest()==v for n,v in m.items())
s=paramiko.SSHClient();s.load_host_keys(str(Path.home()/'.ssh/afc03_motor_known_hosts'));s.connect('192.168.1.89',username='root',key_filename=str(Path.home()/'.ssh/afc03_motor_ed25519'),timeout=8)
f=s.open_sftp();reports=[]
for mode in ('sequential','overlap'):
 f.get(C+'/static-'+mode+'.json',str(H/('static-'+mode+'.json')))
 r=json.loads((H/('static-'+mode+'.json')).read_text());assert r['passed'] and r['count']>=2
 assert r['before']['session']==r['after']['session'] and r['before']['emitted']==r['after']['emitted']
 comparisons=0
 for pos in r['results']:
  pr=pos['report'];assert pr['passed'] and pr['scan_ready']
  for laser in 'AB':
   lr=pr['lasers'][laser];assert lr['strategy']['version']=='fpga-spatial25-rk-localrgb100-160-protected-v1'
   if lr['comparison']:
    assert lr['comparison']['passed'] and lr['comparison']['exact_rational_and_metadata'] and lr['comparison']['mismatch_rows']==0;comparisons+=1
 assert comparisons>=4
 reports.append(r)
s.close()
v=dict(passed=True,sha256=q['sha256'],host_sha256=m,static_modes=reports,motor_moved=False,flash_written=False,cold_boot_tested=False)
(H/'hardware-validation.json').write_text(json.dumps(v,indent=2));q['hardware_validated']=True;(H/'qualified.json').write_text(json.dumps(q,indent=2));print('HARDWARE_AND_PAIRED_HOST_QUALIFIED')
