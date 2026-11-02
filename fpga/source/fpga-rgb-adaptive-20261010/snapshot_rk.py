from pathlib import Path
import paramiko,hashlib,json
H=Path(r'F:/AAA_FPGA/afc03-esp32-motor/fpga-rgb-adaptive-20261010');out=H/'rk-before';out.mkdir(exist_ok=True)
s=paramiko.SSHClient();s.load_host_keys(str(Path.home()/'.ssh/afc03_motor_known_hosts'));s.connect('192.168.1.89',username='root',key_filename=str(Path.home()/'.ssh/afc03_motor_ed25519'),timeout=8)
f=s.open_sftp();report={}
for name in f.listdir('/opt/afc03-scanner/fpga'):
 if name.endswith('.py'):
  dest=out/name;f.get('/opt/afc03-scanner/fpga/'+name,str(dest));local=H/'host'/name;report[name]={'differs':not local.exists() or local.read_bytes()!=dest.read_bytes(),'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()};local.write_bytes(dest.read_bytes())
(H/'rk-before-manifest.json').write_text(json.dumps(report,indent=2));print('Downloaded',len(report),'current runtime modules; differs:',[k for k,v in report.items() if v['differs']]);s.close()
