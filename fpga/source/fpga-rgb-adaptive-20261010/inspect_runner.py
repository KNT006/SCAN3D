from pathlib import Path
import paramiko,hashlib,json
H=Path(r'F:/AAA_FPGA/afc03-esp32-motor/fpga-rgb-adaptive-20261010');s=paramiko.SSHClient();s.load_host_keys(str(Path.home()/'.ssh/afc03_motor_known_hosts'));s.connect('192.168.1.89',username='root',key_filename=str(Path.home()/'.ssh/afc03_motor_ed25519'),timeout=8);f=s.open_sftp()
for name in ('runner.py','replay.py'):
 dest=H/'rk-before-scan3d'/name;dest.parent.mkdir(exist_ok=True);f.get('/opt/afc03-scanner/scan3d/'+name,str(dest))
_,o,e=s.exec_command('cat /userdata/afc03-scanner/jobs/scan3d-work/spatial-profile.json; systemctl is-active afc03-scanner afc03-camera; pgrep -af "scan3d/runner.py|fpga/strategy_scan.py"',timeout=10);print(o.read().decode());print(e.read().decode());s.close()
