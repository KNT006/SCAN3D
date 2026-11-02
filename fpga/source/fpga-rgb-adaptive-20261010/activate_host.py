"""Install the matched RK package only after same-bit hardware validation."""
from pathlib import Path
import hashlib,json,paramiko
H=Path(__file__).resolve().parent
C='/opt/afc03-scanner/candidates/rgb-adaptive-20261010'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
q=json.loads((H/'qualified.json').read_text());v=json.loads((H/'hardware-validation.json').read_text())
assert v['passed'] and q['hardware_validated'] and v['sha256']==q['sha256']
rv=json.loads((H/'runner-validation.json').read_text());assert rv['passed'] and all(sha(Path(p))==h for p,h in rv['sha256'].items())
m=json.loads((H/'host-candidate-manifest.json').read_text());assert m==v['host_sha256']
assert all(sha(H/'host'/n)==h for n,h in m.items())
old={p.name:sha(p) for p in (H/'rk-before').glob('*.py')}
changes={'fpga/'+n:h for n,h in m.items() if old.get(n)!=h}
original={'fpga/'+n:old.get(n) for n in m if old.get(n)!=m[n]}
changes['scan3d/runner.py']=sha(H/'scan3d/runner.py');original['scan3d/runner.py']=sha(H/'rk-before-scan3d/runner.py')
code=r'''
from pathlib import Path
from contextlib import ExitStack
import json,hashlib,shutil,time,fcntl,subprocess,urllib.request
P=Path('/opt/afc03-scanner');C=Path('/opt/afc03-scanner/candidates/rgb-adaptive-20261010')
CH=CHANGES;OLD=ORIGINAL;M=MANIFEST
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
with ExitStack() as stack:
 for name in ('afc03-fpga-scan.lock','afc03-ddr-diag.lock','afc03-rgb-roi-diag.lock'):
  f=stack.enter_context(open('/run/lock/'+name,'a'));fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
 st=json.load(urllib.request.urlopen('http://127.0.0.1:8081/api/status',timeout=5))
 assert not any(st.get(k) for k in ('active_scans','active_jobs','active_calibrations'))
 for n,h in M.items():assert sha(C/'fpga'/n)==h,('staged changed',n)
 for n,h in CH.items():assert sha(C/n)==h
 for n,h in OLD.items():assert (sha(P/n) if (P/n).exists() else None)==h,('production changed',n)
 backup=C/('production-backup-'+str(time.monotonic_ns()));backup.mkdir()
 for n,h in OLD.items():
  if h:
   (backup/n).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(P/n,backup/n)
 installed=[]
 subprocess.run(['systemctl','stop','afc03-scanner'],check=True)
 try:
  for n in CH:
   target=P/(n+'.new');shutil.copy2(C/n,target);target.chmod(0o644);target.replace(P/n);installed.append(n)
  subprocess.run(['/usr/bin/python3','-m','py_compile',*[str(P/n) for n in CH]],check=True)
  subprocess.run(['systemctl','start','afc03-scanner'],check=True)
  for attempt in range(30):
   try:json.load(urllib.request.urlopen('http://127.0.0.1:8081/api/status',timeout=2));break
   except Exception:
    if attempt==29:raise
    time.sleep(.5)
 except BaseException:
  for n in installed:
   if OLD[n]:shutil.copy2(backup/n,P/n)
   else:(P/n).unlink()
  subprocess.run(['systemctl','restart','afc03-scanner'],check=True);raise
 report=dict(passed=True,host_sha256=M,changed_sha256=CH,original_sha256=OLD,fpga_sha256=BIT_SHA,backup=str(backup))
 (C/'deployment.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
'''.replace('CHANGES',repr(changes)).replace('ORIGINAL',repr(original)).replace('MANIFEST',repr(m)).replace('BIT_SHA',repr(q['sha256']))
s=paramiko.SSHClient();s.load_host_keys(str(Path.home()/'.ssh/afc03_motor_known_hosts'));s.connect('192.168.1.89',username='root',key_filename=str(Path.home()/'.ssh/afc03_motor_ed25519'),timeout=8)
try:
 _,o,e=s.exec_command('/usr/bin/python3 -',timeout=60);o.channel.sendall(code.encode());o.channel.shutdown_write();out=o.read().decode();err=e.read().decode();print(out,err);assert o.channel.recv_exit_status()==0
 (H/'activated-host.json').write_text(json.dumps(json.loads(out),indent=2))
finally:s.close()
